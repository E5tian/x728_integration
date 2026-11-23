"""X728 UPS sensors."""

from __future__ import annotations

from datetime import datetime
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfElectricPotential, UnitOfTime
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .coordinator import UPSState, X728Coordinator
from .entity import X728Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        X728Sensor(coordinator, "battery", "Battery", SensorDeviceClass.BATTERY, PERCENTAGE, lambda s: s.capacity, SensorStateClass.MEASUREMENT),
        X728Sensor(coordinator, "voltage", "Battery voltage", SensorDeviceClass.VOLTAGE, UnitOfElectricPotential.VOLT, lambda s: s.voltage, SensorStateClass.MEASUREMENT),
        X728Sensor(coordinator, "ups_status", "UPS status", SensorDeviceClass.ENUM, None, lambda s: s.status, options=["online", "charging", "on_battery", "low_battery", "shutting_down"]),
        X728Sensor(coordinator, "battery_state", "Battery state", SensorDeviceClass.ENUM, None, lambda s: s.battery_state, options=["full", "high", "medium", "low", "critical"]),
        X728Sensor(coordinator, "runtime_estimate", "Estimated runtime", SensorDeviceClass.DURATION, UnitOfTime.MINUTES, lambda s: s.runtime_minutes),
        X728Sensor(coordinator, "time_on_battery", "Time on battery", SensorDeviceClass.DURATION, UnitOfTime.MINUTES, lambda s: round(s.time_on_battery / 60, 1) if s.time_on_battery is not None else 0),
        X728Sensor(coordinator, "last_power_loss", "Last power loss", SensorDeviceClass.TIMESTAMP, None, lambda s: s.last_power_loss),
        X728Sensor(coordinator, "last_power_restored", "Last power restored", SensorDeviceClass.TIMESTAMP, None, lambda s: s.last_power_restored),
        X728Sensor(coordinator, "power_outages", "Power outages", None, None, lambda s: s.outage_count, SensorStateClass.TOTAL_INCREASING),
        X728Sensor(coordinator, "shutdown_countdown", "Shutdown countdown", SensorDeviceClass.DURATION, UnitOfTime.SECONDS, lambda s: s.shutdown_seconds_left),
    ])


class X728Sensor(X728Entity, SensorEntity):
    """Coordinator-backed UPS sensor."""

    def __init__(self, coordinator, key, name, device_class, unit, value_fn, state_class=None, options=None):
        super().__init__(coordinator, key)
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_options = options
        self._value_fn = value_fn
        if key == "battery":
            self._attr_unique_id = "x728_capacity"
        elif key == "voltage":
            self._attr_unique_id = "x728_voltage"

    @property
    def native_value(self):
        return self._value_fn(self.coordinator.data)
