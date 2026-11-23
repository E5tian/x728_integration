"""Geekworm X728 UPS integration."""

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

from .constants import DOMAIN, URL_BASE, CARD_FILENAME, VERSION
from .coordinator import X728Coordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the dashboard card for Lovelace dashboards."""
    await _async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an X728 UPS entry."""
    await _async_register_card(hass)
    coordinator = X728Coordinator(hass, entry)
    try:
        await coordinator.async_open()
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        await coordinator.async_close()
        raise ConfigEntryNotReady(f"Could not initialize X728 UPS hardware: {err}") from err
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload platforms and release I2C/GPIO resources."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_close()
    return unloaded


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the card and inject it so it is available without manual setup."""
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
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(folder), cache_headers=True)]
        )
    except (RuntimeError, ValueError) as err:
        _LOGGER.debug("X728 card static path already registered: %s", err)
    add_extra_js_url(hass, f"{URL_BASE}/{CARD_FILENAME}?v={VERSION}-{fingerprint}")
    hass.data[DOMAIN]["card_registered"] = True
