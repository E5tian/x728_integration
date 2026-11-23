"""X728 power and battery binary sensors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import X728Coordinator
from .entity import X728Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities([
        X728BinarySensor(coordinator, "ac_power", "AC power", BinarySensorDeviceClass.PLUG, lambda s: s.ac_present),
        X728BinarySensor(coordinator, "battery_charging", "Battery charging", BinarySensorDeviceClass.BATTERY_CHARGING, lambda s: s.is_charging),
        X728BinarySensor(coordinator, "battery_low", "Battery low", BinarySensorDeviceClass.BATTERY, lambda s: s.capacity < coordinator.low_battery_threshold),
        X728BinarySensor(coordinator, "power_loss", "Power loss", BinarySensorDeviceClass.PROBLEM, lambda s: not s.ac_present),
    ])


class X728BinarySensor(X728Entity, BinarySensorEntity):
    def __init__(self, coordinator: X728Coordinator, key: str, name: str, device_class, value_fn) -> None:
        super().__init__(coordinator, key)
        self._attr_name = name
        self._attr_device_class = device_class
        self._value_fn = value_fn

    @property
    def is_on(self) -> bool:
        return self._value_fn(self.coordinator.data)
