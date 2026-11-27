"""Polling coordinator and UPS policy for Geekworm X728."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import time
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .constants import (
    CHARGE_LIMIT_FLOOR,
    CONF_LOW_BATTERY,
    CONF_SCAN_INTERVAL,
    DEFAULT_CHARGE_LIMIT_MAX,
    DEFAULT_CHARGE_LIMIT_MIN,
    DEFAULT_LOW_BATTERY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SHUTDOWN_AFTER_MINUTES,
    DEFAULT_SHUTDOWN_BELOW,
    DOMAIN,
    EVENT_SHUTDOWN,
    RUNTIME_MAX_MINUTES,
    RUNTIME_MIN_DROP_PERCENT,
    RUNTIME_MIN_SECONDS,
    SHUTDOWN_AFTER_MINUTES_MAX,
    SHUTDOWN_BELOW_MAX,
    SHUTDOWN_BELOW_MIN,
    SHUTDOWN_CONFIRM_SECONDS,
    SHUTDOWN_REASON_LEVEL,
    SHUTDOWN_REASON_TIME,
    SHUTDOWN_STARTUP_GRACE_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
    UPS_STATUS_CHARGING,
    UPS_STATUS_LOW_BATTERY,
    UPS_STATUS_ON_BATTERY,
    UPS_STATUS_ONLINE,
    UPS_STATUS_SHUTTING_DOWN,
)
from .hardware import Sample, X728Hardware, X728HardwareError

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UPSState:
    """Immutable snapshot shared by all UPS entities."""

    voltage: float
    capacity: float
    ac_present: bool
    charging_allowed: bool
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
    """Owns X728 resources and coordinates polling, history and UPS actions."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        interval = int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(5, interval)),
            request_refresh_debouncer=Debouncer(hass, _LOGGER, cooldown=1, immediate=True),
        )
        self.hass = hass
        self.config_entry = entry
        self.hardware = X728Hardware(
            int(entry.data.get("i2c_bus", 1)),
            int(entry.data.get("i2c_address", 0x36)),
            bool(entry.data.get("charge_control", False)),
        )
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._reader_fd: int | None = None
        self._started_at = time.monotonic()
        self._on_battery_since: float | None = None
        self._on_battery_start_capacity: float | None = None
        self._resume_outage_from: datetime | None = None
        self._shutdown_armed_at: float | None = None
        self._shutdown_reason: str | None = None
        self._shutdown_requested = False
        self._closed = False

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

    @property
    def low_battery_threshold(self) -> int:
        return int(self.config_entry.data.get(CONF_LOW_BATTERY, DEFAULT_LOW_BATTERY))

    @property
    def effective_charge_limit_min(self) -> float:
        return min(self.charge_limit_min, self.charge_limit_max)

    @property
    def shutdown_seconds_left(self) -> int | None:
        if self._shutdown_armed_at is None or self._shutdown_requested:
            return None
        return max(0, round(SHUTDOWN_CONFIRM_SECONDS - (time.monotonic() - self._shutdown_armed_at)))

    @property
    def time_on_battery(self) -> int | None:
        return None if self._on_battery_since is None else int(time.monotonic() - self._on_battery_since)

    @property
    def host_shutdown_available(self) -> bool:
        return self.hass.services.has_service("hassio", "host_shutdown")

    async def async_load_settings(self) -> None:
        """Restore persistent settings and outage history."""
        stored = await self._store.async_load()
        if not stored:
            return
        self.charging_switch_on = bool(stored.get("charging_switch_on", True))
        self.charge_limit_min = float(stored.get("charge_limit_min", DEFAULT_CHARGE_LIMIT_MIN))
        self.charge_limit_max = float(stored.get("charge_limit_max", DEFAULT_CHARGE_LIMIT_MAX))
        self.shutdown_enabled = bool(stored.get("shutdown_enabled", False))
        self.shutdown_below = float(stored.get("shutdown_below", DEFAULT_SHUTDOWN_BELOW))
        self.shutdown_after_minutes = int(stored.get("shutdown_after_minutes", DEFAULT_SHUTDOWN_AFTER_MINUTES))
        rate = stored.get("learned_rate")
        self.learned_rate = float(rate) if rate else None
        self.outage_count = int(stored.get("outage_count", 0))
        self.last_power_loss = _parse_datetime(stored.get("last_power_loss"))
        self.last_power_restored = _parse_datetime(stored.get("last_power_restored"))
        if stored.get("outage_active") and self.last_power_loss:
            self._resume_outage_from = self.last_power_loss

    def _settings_to_save(self) -> dict[str, Any]:
        return {
            "charging_switch_on": self.charging_switch_on,
            "charge_limit_min": self.charge_limit_min,
            "charge_limit_max": self.charge_limit_max,
            "shutdown_enabled": self.shutdown_enabled,
            "shutdown_below": self.shutdown_below,
            "shutdown_after_minutes": self.shutdown_after_minutes,
            "learned_rate": self.learned_rate,
            "outage_count": self.outage_count,
            "last_power_loss": _format_datetime(self.last_power_loss),
            "last_power_restored": _format_datetime(self.last_power_restored),
            "outage_active": self._on_battery_since is not None or self._resume_outage_from is not None,
        }

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._settings_to_save, 2)

    async def async_open(self) -> None:
        """Open I2C/GPIO resources away from the event loop."""
        try:
            await self.hass.async_add_executor_job(self.hardware.open)
            self._reader_fd = self.hardware.event_fd
            self.hass.loop.add_reader(self._reader_fd, self._handle_gpio_event)
        except Exception as err:
            await self.hass.async_add_executor_job(self.hardware.close)
            raise UpdateFailed(f"Could not open X728 hardware: {err}") from err

    async def async_close(self) -> None:
        """Release all claimed resources and persist the last state."""
        if self._reader_fd is not None:
            self.hass.loop.remove_reader(self._reader_fd)
            self._reader_fd = None
        if not self._closed:
            self._closed = True
            await self.hass.async_add_executor_job(self.hardware.close)
            await self._store.async_save(self._settings_to_save())

    @callback
    def _handle_gpio_event(self) -> None:
        self.hardware.drain_events()
        self.hass.async_create_task(self.async_request_refresh())

    async def async_set_charging(self, enabled: bool) -> None:
        self.charging_switch_on = enabled
        self._schedule_save()
        await self.async_request_refresh()

    async def async_set_charge_limit(self, *, minimum: float | None = None, maximum: float | None = None) -> None:
        if minimum is not None:
            self.charge_limit_min = max(CHARGE_LIMIT_FLOOR, min(100.0, minimum))
        if maximum is not None:
            self.charge_limit_max = max(CHARGE_LIMIT_FLOOR, min(100.0, maximum))
        self._schedule_save()
        await self.async_request_refresh()

    def _charge_target(self, capacity: float) -> bool:
        if capacity >= self.charge_limit_max:
            return False
        if capacity <= self.effective_charge_limit_min:
            return self.charging_switch_on
        # Between limits preserve the existing user permission. On initial
        # startup that permission is true; stopping at the upper limit remains latched.
        return self.charging_switch_on and self.hardware.charging_allowed

    async def async_set_shutdown(self, *, enabled: bool | None = None, below: float | None = None, after_minutes: int | None = None) -> None:
        if enabled is not None:
            self.shutdown_enabled = enabled
        if below is not None:
            self.shutdown_below = min(SHUTDOWN_BELOW_MAX, max(SHUTDOWN_BELOW_MIN, below))
        if after_minutes is not None:
            self.shutdown_after_minutes = int(min(SHUTDOWN_AFTER_MINUTES_MAX, max(0, after_minutes)))
        self._disarm_shutdown()
        self._schedule_save()
        await self.async_request_refresh()

    def _disarm_shutdown(self) -> None:
        self._shutdown_armed_at = None
        self._shutdown_reason = None
        self._shutdown_requested = False
        persistent_notification.async_dismiss(self.hass, self._notification_id)

    @property
    def _notification_id(self) -> str:
        return f"{DOMAIN}_shutdown_{self.config_entry.entry_id}"

    def _shutdown_condition(self, sample: Sample) -> str | None:
        if not self.shutdown_enabled or sample.ac_present:
            return None
        if sample.capacity <= self.shutdown_below:
            return SHUTDOWN_REASON_LEVEL
        if self.shutdown_after_minutes and (self.time_on_battery or 0) >= self.shutdown_after_minutes * 60:
            return SHUTDOWN_REASON_TIME
        return None

    def _evaluate_shutdown(self, sample: Sample) -> None:
        reason = self._shutdown_condition(sample)
        if reason is None:
            if self._shutdown_armed_at is not None:
                self._disarm_shutdown()
            return
        now = time.monotonic()
        if now - self._started_at < SHUTDOWN_STARTUP_GRACE_SECONDS or self._shutdown_requested:
            return
        if self._shutdown_armed_at is None:
            self._shutdown_armed_at = now
            self._shutdown_reason = reason
            persistent_notification.async_create(
                self.hass,
                f"X728: Battery shutdown condition ({reason}) is active. The host will shut down in {SHUTDOWN_CONFIRM_SECONDS} seconds unless mains power returns.",
                title="UPS shutdown pending",
                notification_id=self._notification_id,
            )
            return
        if now - self._shutdown_armed_at >= SHUTDOWN_CONFIRM_SECONDS:
            self._shutdown_requested = True
            self.hass.async_create_task(self._async_shutdown(sample, reason))

    async def _async_shutdown(self, sample: Sample, reason: str) -> None:
        self.hass.bus.async_fire(EVENT_SHUTDOWN, {
            "entry_id": self.config_entry.entry_id, "reason": reason,
            "capacity": sample.capacity, "voltage": sample.voltage,
            "threshold": self.shutdown_below, "after_minutes": self.shutdown_after_minutes,
            "time_on_battery": self.time_on_battery,
        })
        await self._store.async_save(self._settings_to_save())
        if self.host_shutdown_available:
            await self.hass.services.async_call("hassio", "host_shutdown", blocking=False)
        else:
            persistent_notification.async_create(
                self.hass,
                f"Automatic host shutdown is unavailable. An event {EVENT_SHUTDOWN} was fired for an automation to handle.",
                title="UPS shutdown action required",
                notification_id=self._notification_id,
            )

    def _track_outage(self, sample: Sample) -> None:
        now = time.monotonic()
        if not sample.ac_present and self._on_battery_since is None:
            if self._resume_outage_from is not None:
                elapsed = max(0.0, (dt_util.utcnow() - self._resume_outage_from).total_seconds())
                self._on_battery_since = now - elapsed
                self._on_battery_start_capacity = sample.capacity
                self._resume_outage_from = None
                return
            self._on_battery_since = now
            self._on_battery_start_capacity = sample.capacity
            self.outage_count += 1
            self.last_power_loss = dt_util.utcnow()
            self._schedule_save()
        elif sample.ac_present and self._on_battery_since is not None:
            rate = self._current_rate(sample)
            if rate is not None:
                self.learned_rate = rate if self.learned_rate is None else 0.5 * (self.learned_rate + rate)
            self._on_battery_since = None
            self._on_battery_start_capacity = None
            self.last_power_restored = dt_util.utcnow()
            self._schedule_save()

    def _current_rate(self, sample: Sample) -> float | None:
        if self._on_battery_since is None or self._on_battery_start_capacity is None:
            return None
        elapsed = time.monotonic() - self._on_battery_since
        drop = self._on_battery_start_capacity - sample.capacity
        return drop / elapsed * 3600 if elapsed >= RUNTIME_MIN_SECONDS and drop >= RUNTIME_MIN_DROP_PERCENT else None

    def _runtime_minutes(self, sample: Sample) -> int | None:
        rate = self._current_rate(sample) or self.learned_rate
        if not rate or rate <= 0:
            return None
        return int(min(RUNTIME_MAX_MINUTES, max(0.0, sample.capacity / rate * 60)))

    def _status(self, sample: Sample) -> str:
        if self._shutdown_armed_at is not None or self._shutdown_requested:
            return UPS_STATUS_SHUTTING_DOWN
        if not sample.ac_present:
            return UPS_STATUS_LOW_BATTERY if sample.capacity < self.low_battery_threshold else UPS_STATUS_ON_BATTERY
        if self.hardware.charging_allowed and sample.capacity < 99:
            return UPS_STATUS_CHARGING
        return UPS_STATUS_ONLINE

    async def _async_update_data(self) -> UPSState:
        try:
            sample = await self.hass.async_add_executor_job(self.hardware.read)
            self._track_outage(sample)
            if self.hardware.charge_control:
                target = self._charge_target(sample.capacity)
                if target != self.hardware.charging_allowed:
                    await self.hass.async_add_executor_job(self.hardware.set_charging, target)
            self._evaluate_shutdown(sample)
        except (X728HardwareError, OSError) as err:
            raise UpdateFailed(str(err)) from err
        return UPSState(
            voltage=sample.voltage,
            capacity=sample.capacity,
            ac_present=sample.ac_present,
            charging_allowed=self.hardware.charging_allowed,
            is_charging=(sample.ac_present and self.hardware.charging_allowed and sample.capacity < 99),
            battery_state=sample.battery_state,
            status=self._status(sample),
            time_on_battery=self.time_on_battery,
            runtime_minutes=self._runtime_minutes(sample),
            shutdown_seconds_left=self.shutdown_seconds_left,
            shutdown_reason=self._shutdown_reason,
            last_power_loss=self.last_power_loss,
            last_power_restored=self.last_power_restored,
            outage_count=self.outage_count,
        )


def _parse_datetime(value: Any) -> datetime | None:
    return dt_util.parse_datetime(str(value)) if value else None


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
