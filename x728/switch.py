"""User controls for X728 charging and safe shutdown."""

from typing import Any
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import X728Coordinator
from .entity import X728Entity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities = [AutoShutdownSwitch(coordinator)]
    if coordinator.hardware.charge_control:
        entities.append(ChargingSwitch(coordinator))
    async_add_entities(entities)


class ChargingSwitch(X728Entity, SwitchEntity):
    def __init__(self, coordinator):
        super().__init__(coordinator, "charging")
        self._attr_name = "Battery charging"

    @property
    def is_on(self) -> bool:
        return self.coordinator.charging_switch_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_charging(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_charging(False)


class AutoShutdownSwitch(X728Entity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator):
        super().__init__(coordinator, "auto_shutdown")
        self._attr_name = "Automatic shutdown"

    @property
    def is_on(self) -> bool:
        return self.coordinator.shutdown_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_shutdown(enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_shutdown(enabled=False)
