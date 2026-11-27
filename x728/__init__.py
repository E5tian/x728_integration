"""Geekworm X728 UPS integration setup."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .constants import CARD_FILENAME, DOMAIN, URL_BASE, VERSION
from .coordinator import X728Coordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    await _async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize the coordinator and forward its entity platforms."""
    await _async_register_card(hass)
    coordinator = X728Coordinator(hass, entry)
    await coordinator.async_load_settings()
    try:
        await coordinator.async_open()
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        await coordinator.async_close()
        raise ConfigEntryNotReady(f"Could not initialize X728 UPS hardware: {err}") from err
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard module, with a content hash for browser cache busting."""
    if hass.data.setdefault(DOMAIN, {}).get("card_registered"):
        return
    folder = Path(__file__).parent / "frontend"
    card = folder / CARD_FILENAME
    try:
        fingerprint = await hass.async_add_executor_job(lambda: hashlib.sha256(card.read_bytes()).hexdigest()[:10])
    except OSError:
        _LOGGER.warning("X728 dashboard card missing: %s", card)
        return
    try:
        await hass.http.async_register_static_paths([StaticPathConfig(URL_BASE, str(folder), cache_headers=True)])
    except (RuntimeError, ValueError) as err:
        _LOGGER.debug("X728 card static path already registered: %s", err)
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}?v={VERSION}-{fingerprint}")
    hass.data[DOMAIN]["card_registered"] = True
