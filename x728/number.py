"""Configuration numbers for X728 charging and shutdown thresholds."""

from collections.abc import Callable, Awaitable
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .constants import CHARGE_LIMIT_FLOOR, SHUTDOWN_AFTER_MINUTES_MAX, SHUTDOWN_BELOW_MAX, SHUTDOWN_BELOW_MIN
from .coordinator import X728Coordinator
from .entity import X728Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = [
        X728Number(coordinator, "shutdown_below", "Shut down below", PERCENTAGE, SHUTDOWN_BELOW_MIN, SHUTDOWN_BELOW_MAX, lambda c: c.shutdown_below, lambda c, v: c.async_set_shutdown(below=v)),
        X728Number(coordinator, "shutdown_after_minutes", "Shut down after minutes", UnitOfTime.MINUTES, 0, SHUTDOWN_AFTER_MINUTES_MAX, lambda c: c.shutdown_after_minutes, lambda c, v: c.async_set_shutdown(after_minutes=int(v)), mode=NumberMode.BOX),
    ]
    if coordinator.hardware.charge_control:
        entities.extend([
            X728Number(coordinator, "charge_limit_min", "Charge limit minimum", PERCENTAGE, CHARGE_LIMIT_FLOOR, 100, lambda c: c.charge_limit_min, lambda c, v: c.async_set_charge_limit(minimum=v)),
            X728Number(coordinator, "charge_limit_max", "Charge limit maximum", PERCENTAGE, CHARGE_LIMIT_FLOOR, 100, lambda c: c.charge_limit_max, lambda c, v: c.async_set_charge_limit(maximum=v)),
        ])
    async_add_entities(entities)


class X728Number(X728Entity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: X728Coordinator, key: str, name: str, unit: str, minimum: float, maximum: float, get_value: Callable, set_value: Callable, mode=NumberMode.SLIDER):
        super().__init__(coordinator, key)
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = 1
        self._attr_mode = mode
        self._get_value = get_value
        self._set_value = set_value

    @property
    def native_value(self) -> float:
        return self._get_value(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        await self._set_value(self.coordinator, value)
