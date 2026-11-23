"""X728 UPS hardware access. All blocking operations run in an executor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import glob
import logging

import gpiod
from gpiod.line import Bias, Direction, Edge, Value
import smbus2

from .constants import PIN_CHARGING, PIN_POWER_LOSS, REG_CAPACITY, REG_VOLTAGE

_LOGGER = logging.getLogger(__name__)


class X728HardwareError(Exception):
    """Hardware I/O or GPIO configuration failure."""


@dataclass(frozen=True, slots=True)
class Sample:
    voltage: float
    capacity: float
    ac_present: bool

    @property
    def battery_state(self) -> str:
        if self.capacity >= 95:
            return "full"
        if self.capacity >= 60:
            return "high"
        if self.capacity >= 30:
            return "medium"
        if self.capacity >= 10:
            return "low"
        return "critical"


def _swap16(value: int) -> int:
    return ((value << 8) & 0xFF00) | (value >> 8)


def _gpiochip() -> str:
    """Find the GPIO controller for the Raspberry Pi header."""
    for path in sorted(glob.glob("/dev/gpiochip*")):
        try:
            with gpiod.Chip(path) as chip:
                if chip.get_info().label.startswith(("pinctrl-rp1", "pinctrl-bcm")):
                    return path
        except OSError:
            continue
    raise X728HardwareError("Could not find a Raspberry Pi GPIO chip for the 40-pin header")


class X728Hardware:
    """Owns the fuel gauge and GPIO handles while the integration is loaded."""

    def __init__(self, bus_number: int, address: int, charge_control: bool) -> None:
        self.bus_number = bus_number
        self.address = address
        self.charge_control = charge_control
        self._bus: smbus2.SMBus | None = None
        self._chip: gpiod.Chip | None = None
        self._power_request: gpiod.LineRequest | None = None
        self._charge_request: gpiod.LineRequest | None = None
        self.charging_allowed = True

    def open(self) -> None:
        try:
            self._bus = smbus2.SMBus(self.bus_number)
            self._chip = gpiod.Chip(_gpiochip())
            self._power_request = self._chip.request_lines(
                consumer="x728_power_loss",
                config={PIN_POWER_LOSS: gpiod.LineSettings(
                    direction=Direction.INPUT, bias=Bias.PULL_UP,
                    edge_detection=Edge.BOTH, debounce_period=timedelta(milliseconds=50),
                )},
            )
            if self.charge_control:
                self._charge_request = self._chip.request_lines(
                    consumer="x728_charge_control",
                    config={PIN_CHARGING: gpiod.LineSettings(
                        direction=Direction.OUTPUT,
                        output_value=Value.ACTIVE,
                    )},
                )
            self.read()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        for name in ("_charge_request", "_power_request"):
            request = getattr(self, name)
            if request is not None:
                try:
                    request.release()
                except OSError:
                    pass
                setattr(self, name, None)
        if self._chip is not None:
            self._chip.close()
            self._chip = None
        if self._bus is not None:
            try:
                self._bus.close()
            except OSError:
                pass
            self._bus = None

    @property
    def event_fd(self) -> int:
        if self._power_request is None:
            raise X728HardwareError("GPIO is not initialized")
        return self._power_request.fd

    def drain_events(self) -> None:
        if self._power_request is not None:
            try:
                self._power_request.read_edge_events()
            except OSError as err:
                _LOGGER.debug("Could not drain X728 GPIO event: %s", err)

    def read(self) -> Sample:
        if self._bus is None or self._power_request is None:
            raise X728HardwareError("X728 hardware is not open")
        try:
            raw_voltage = _swap16(self._bus.read_word_data(self.address, REG_VOLTAGE))
            raw_capacity = _swap16(self._bus.read_word_data(self.address, REG_CAPACITY))
            power_lost = self._power_request.get_value(PIN_POWER_LOSS) == Value.ACTIVE
        except OSError as err:
            raise X728HardwareError(f"Unable to read X728: {err}") from err
        # Fuel-gauge voltage is 78.125 uV/LSB; capacity is 1/256 percent/LSB.
        return Sample(
            voltage=round(raw_voltage * 78.125 / 1_000_000, 3),
            capacity=round(min(100.0, max(0.0, raw_capacity / 256)), 2),
            ac_present=not power_lost,
        )

    def set_charging(self, enabled: bool) -> None:
        """Set GPIO16 (X728 V2.5 only): high enables, low disables charging."""
        if not self.charge_control or self._charge_request is None:
            raise X728HardwareError("Charging GPIO control is disabled or unsupported")
        try:
            self._charge_request.set_value(PIN_CHARGING, Value.ACTIVE if enabled else Value.INACTIVE)
        except OSError as err:
            raise X728HardwareError(f"Could not set X728 charging GPIO: {err}") from err
        self.charging_allowed = enabled
