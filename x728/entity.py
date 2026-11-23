"""Shared entity helpers for the X728 integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .constants import DOMAIN
from .coordinator import X728Coordinator


class X728Entity(CoordinatorEntity[X728Coordinator]):
    """Attach every entity to the same UPS device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: X728Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "x728")}, manufacturer="Geekworm",
            name="Geekworm X728 UPS", model="X728",
        )
