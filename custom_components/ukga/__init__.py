"""UK Gay Saunas directory and events integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SOURCES, SCAN_INTERVAL
from .scraper import async_collect

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["calendar", "button", "sensor"]

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    sources = entry.data.get("sources", DEFAULT_SOURCES)

    async def async_update_data():
        try:
            return await async_collect(session, sources)
        except Exception as err:
            raise UpdateFailed(f"Could not refresh UK sauna sources: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass, _LOGGER, name=DOMAIN, update_method=async_update_data,
        update_interval=timedelta(minutes=SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(hass, entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
