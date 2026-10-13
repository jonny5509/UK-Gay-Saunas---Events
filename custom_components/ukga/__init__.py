"""UK Gay Saunas directory and events integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SOURCES, SCAN_INTERVAL
from .scraper import async_collect

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["calendar", "button", "sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    # Keep existing installations aligned with the fixed England regional directory list.
    sources = list(DEFAULT_SOURCES)
    if entry.data.get("sources") != sources:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "sources": sources}
        )

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

    # Register a parent hub device; each sauna is exposed as a child device.
    device_registry = async_get_device_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="UKGA Sauna Hub",
        manufacturer="UK Gay Saunas & Events",
        model="Sauna directory and events hub",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
