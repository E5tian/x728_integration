"""Polling and UPS state management for the X728."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .constants import *  # noqa: F403
from .hardware import Sample, X728Hardware, X728HardwareError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UPSState:
    voltage: float
    capacity: float
    ac_present: bool
    is_charging: bool
    battery_state: str
    status: str
    time_on_battery: int | None
    runtime_minutes: int | None
    shutdown_seconds_left: int | None
    shutdown_reason: str | None
    last_power_loss: datetime | None
    last_power_restored: datetime | None
    outage_count: int


class X728Coordinator(DataUpdateCoordinator[UPSState]):
    """Owns I2C/GPIO hardware and implements charge, runtime and shutdown rules."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.hardware = X728Hardware(
            entry.data.get(CONF_I2C_BUS, DEFAULT_I2C_BUS),
            entry.data.get(CONF_I2C_ADDRESS, DEFAULT_I2C_ADDRESS),
            entry.data.get(CONF_CHARGE_CONTROL, False),
        )
        super().__init__(hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)))
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self.low_battery_threshold = int(entry.data.get(CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY))
        self.charging_switch_on = True
        self.charge_limit_min = DEFAULT_CHARGE_LIMIT_MIN
        self.charge_limit_max = DEFAULT_CHARGE_LIMIT_MAX
        self.shutdown_enabled = False
        self.shutdown_below = DEFAULT_SHUTDOWN_BELOW
        self.shutdown_after_minutes = DEFAULT_SHUTDOWN_AFTER_MINUTES
        self.learned_rate: float | None = None
        self.outage_count = 0
        self.last_power_loss: datetime | None = None
        self.last_power_restored: datetime | None = None
        self._started = time.monotonic()
        self._battery_since: float | None = None
        self._battery_start_capacity: float | None = None
        self._resume_outage: datetime | None = None
        self._window_allows = True
        self._shutdown_armed: float | None = None
        self._shutdown_reason: str | None = None
        self._shutdown_requested = False
        self._reader_fd: int | None = None

    @property
    def time_on_battery(self) -> int | None:
        return int(time.monotonic() - self._battery_since) if self._battery_since is not None else None

    @property
    def shutdown_seconds_left(self) -> int | None:
        if self._shutdown_armed is None or self._shutdown_requested:
            return None
        return max(0, round(SHUTDOWN_CONFIRM_SECONDS - (time.monotonic() - self._shutdown_armed)))

    @property
    def host_shutdown_available(self) -> bool:
        return self.hass.services.has_service("hassio", "host_shutdown")

    async def async_open(self) -> None:
        stored = await self._store.async_load() or {}
        self.charging_switch_on = bool(stored.get("charging_switch_on", True))
        self.charge_limit_min = float(stored.get("charge_limit_min", DEFAULT_CHARGE_LIMIT_MIN))
        self.charge_limit_max = float(stored.get("charge_limit_max", DEFAULT_CHARGE_LIMIT_MAX))
        self.shutdown_enabled = bool(stored.get("shutdown_enabled", False))
        self.shutdown_below = float(stored.get("shutdown_below", DEFAULT_SHUTDOWN_BELOW))
        self.shutdown_after_minutes = int(stored.get("shutdown_after_minutes", 0))
        self.learned_rate = stored.get("learned_rate")
        self.outage_count = int(stored.get("outage_count", 0))
        self.last_power_loss = dt_util.parse_datetime(stored.get("last_power_loss", ""))
        self.last_power_restored = dt_util.parse_datetime(stored.get("last_power_restored", ""))
        if stored.get("outage_active"):
            self._resume_outage = self.last_power_loss
        if self.hardware.charge_control:
            self.hardware.charging_allowed = self.charging_switch_on
        try:
            await self.hass.async_add_executor_job(self.hardware.open)
        except Exception as err:
            raise UpdateFailed(str(err)) from err
        self._reader_fd = self.hardware.event_fd
        self.hass.loop.add_reader(self._reader_fd, self._gpio_event)

    async def async_close(self) -> None:
        if self._reader_fd is not None:
            self.hass.loop.remove_reader(self._reader_fd)
            self._reader_fd = None
        await self.hass.async_add_executor_job(self.hardware.close)
        await self._store.async_save(self._settings())

    @callback
    def _gpio_event(self) -> None:
        self.hardware.drain_events()
        self.hass.async_create_task(self.async_request_refresh())

    def _settings(self) -> dict[str, Any]:
        return {
            "charging_switch_on": self.charging_switch_on,
            "charge_limit_min": self.charge_limit_min,
            "charge_limit_max": self.charge_limit_max,
            "shutdown_enabled": self.shutdown_enabled,
            "shutdown_below": self.shutdown_below,
            "shutdown_after_minutes": self.shutdown_after_minutes,
            "learned_rate": self.learned_rate,
            "outage_count": self.outage_count,
            "last_power_loss": self.last_power_loss.isoformat() if self.last_power_loss else None,
            "last_power_restored": self.last_power_restored.isoformat() if self.last_power_restored else None,
            "outage_active": self._battery_since is not None,
        }

    @callback
    def _save_later(self) -> None:
        self._store.async_delay_save(self._settings, 2)

    async def async_set_charging(self, enabled: bool) -> None:
        self.charging_switch_on = enabled
        if enabled:
            self._window_allows = True
        self._save_later()
        await self.async_request_refresh()

    async def async_set_charge_limit(self, minimum: float | None = None, maximum: float | None = None) -> None:
        if minimum is not None:
            self.charge_limit_min = min(100, max(CHARGE_LIMIT_FLOOR, minimum))
        if maximum is not None:
            self.charge_limit_max = min(100, max(CHARGE_LIMIT_FLOOR, maximum))
        self._window_allows = True
        self._save_later()
        await self.async_request_refresh()

    async def async_set_shutdown(self, enabled: bool | None = None, below: float | None = None, after_minutes: int | None = None) -> None:
        if enabled is not None:
            self.shutdown_enabled = enabled
        if below is not None:
            self.shutdown_below = min(SHUTDOWN_BELOW_MAX, max(SHUTDOWN_BELOW_MIN, below))
        if after_minutes is not None:
            self.shutdown_after_minutes = max(0, min(SHUTDOWN_AFTER_MINUTES_MAX, int(after_minutes)))
        self._shutdown_armed = None
        self._shutdown_reason = None
        self._shutdown_requested = False
        self._save_later()
        await self.async_request_refresh()

    def _track_outage(self, sample: Sample) -> None:
        now = time.monotonic()
        if not sample.ac_present and self._battery_since is None:
            if self._resume_outage is not None:
                elapsed = max(0, (dt_util.utcnow() - self._resume_outage).total_seconds())
                self._battery_since = now - elapsed
                self._battery_start_capacity = sample.capacity
                self._resume_outage = None
                return
            self._battery_since = now
            self._battery_start_capacity = sample.capacity
            self.outage_count += 1
            self.last_power_loss = dt_util.utcnow()
            self._save_later()
        elif sample.ac_present and self._battery_since is not None:
            rate = self._current_rate(sample)
            if rate:
                self.learned_rate = rate if self.learned_rate is None else (self.learned_rate + rate) / 2
            self._battery_since = self._battery_start_capacity = None
            self.last_power_restored = dt_util.utcnow()
            self._save_later()

    def _current_rate(self, sample: Sample) -> float | None:
        if self._battery_since is None or self._battery_start_capacity is None:
            return None
        elapsed = time.monotonic() - self._battery_since
        drop = self._battery_start_capacity - sample.capacity
        return drop / elapsed * 3600 if elapsed >= RUNTIME_MIN_SECONDS and drop >= RUNTIME_MIN_DROP_PERCENT else None

    def _shutdown(self, sample: Sample) -> None:
        reason = None
        if self.shutdown_enabled and not sample.ac_present:
            if sample.capacity <= self.shutdown_below:
                reason = "battery_level"
            elif self.shutdown_after_minutes and (self.time_on_battery or 0) >= self.shutdown_after_minutes * 60:
                reason = "time_on_battery"
        if reason is None:
            self._shutdown_armed = None
            self._shutdown_reason = None
            self._shutdown_requested = False
            return
        now = time.monotonic()
        if now - self._started < SHUTDOWN_STARTUP_GRACE_SECONDS:
            return
        if self._shutdown_armed is None:
            self._shutdown_armed = now
            self._shutdown_reason = reason
            persistent_notification.async_create(self.hass,
                f"X728 is on battery ({sample.capacity:.0f}%). Host shutdown in {SHUTDOWN_CONFIRM_SECONDS} seconds unless power returns.",
                title="X728 UPS shutdown pending", notification_id=f"x728_shutdown_{self.entry.entry_id}")
            return
        if now - self._shutdown_armed >= SHUTDOWN_CONFIRM_SECONDS and not self._shutdown_requested:
            self._shutdown_requested = True
            self.hass.async_create_task(self._async_shutdown(sample, reason))

    async def _async_shutdown(self, sample: Sample, reason: str) -> None:
        self.hass.bus.async_fire(EVENT_SHUTDOWN, {
            "entry_id": self.entry.entry_id, "reason": reason,
            "capacity": sample.capacity, "voltage": sample.voltage,
            "time_on_battery": self.time_on_battery,
        })
        await self._store.async_save(self._settings())
        if self.host_shutdown_available:
            await self.hass.services.async_call("hassio", "host_shutdown", blocking=False)
        else:
            persistent_notification.async_create(self.hass,
                f"Automatic shutdown requested. Listen for the {EVENT_SHUTDOWN} event to shut down this host.",
                title="X728 host shutdown unavailable", notification_id=f"x728_shutdown_{self.entry.entry_id}")

    async def _async_update_data(self) -> UPSState:
        try:
            sample = await self.hass.async_add_executor_job(self.hardware.read)
        except X728HardwareError as err:
            raise UpdateFailed(str(err)) from err
        self._track_outage(sample)
        if self.hardware.charge_control:
            if sample.capacity >= self.charge_limit_max:
                self._window_allows = False
            elif sample.capacity <= min(self.charge_limit_min, self.charge_limit_max):
                self._window_allows = True
            target = self.charging_switch_on and self._window_allows
            if target != self.hardware.charging_allowed:
                await self.hass.async_add_executor_job(self.hardware.set_charging, target)
        self._shutdown(sample)
        current_rate = self._current_rate(sample) or self.learned_rate
        runtime = int(min(RUNTIME_MAX_MINUTES, sample.capacity / current_rate * 60)) if current_rate and current_rate > 0 else None
        is_charging = sample.ac_present and self.hardware.charging_allowed and sample.capacity < 99
        if self._shutdown_armed is not None or self._shutdown_requested:
            status = "shutting_down"
        elif not sample.ac_present:
            status = "low_battery" if sample.capacity < self.low_battery_threshold else "on_battery"
        else:
            status = "charging" if is_charging else "online"
        return UPSState(sample.voltage, sample.capacity, sample.ac_present, is_charging,
            sample.battery_state, status, self.time_on_battery, runtime,
            self.shutdown_seconds_left, self._shutdown_reason, self.last_power_loss,
            self.last_power_restored, self.outage_count)
