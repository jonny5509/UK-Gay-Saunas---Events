"""UK Gay Saunas directory and events integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import hashlib

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components import persistent_notification

from .const import DOMAIN, DEFAULT_SOURCES, SCAN_INTERVAL
from .scraper import async_collect
from .favourites import FavouriteStore

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["calendar", "button", "sensor", "switch"]


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

    favourite_store = FavouriteStore(hass, entry.entry_id)
    await favourite_store.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id + "_favourites"] = favourite_store
    async def async_update_data():
        try:
            data = await async_collect(session, sources)
            from .sensor import _event_matches_venue, _event_start
            from .favourites import venue_key

            events = data.get("events", [])
            venues = data.get("venues", [])
            now = datetime.now().astimezone()
            reminder_deadline = now + timedelta(hours=24)
            processed_event_keys = set()
            for event in events:
                start = _event_start(event)
                # Send a reminder during the 24 hours before an event starts.
                if not start or start <= now or start > reminder_deadline:
                    continue
                identity = "|".join(str(event.get(field) or "") for field in (
                    "summary", "start", "end", "url", "location"
                ))
                event_fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                for venue in venues:
                    if not favourite_store.notifications_enabled(venue):
                        continue
                    if not _event_matches_venue(event, venue):
                        continue
                    # Track reminders per venue, so one event can notify each
                    # subscribed sauna independently and only once.
                    reminder_key = "reminder:" + hashlib.sha256(
                        f"{event_fingerprint}|{venue_key(venue)}".encode("utf-8")
                    ).hexdigest()
                    if reminder_key in favourite_store.notified_events:
                        continue
                    name = venue.get("name") or "Sauna"
                    summary = event.get("summary") or "Upcoming event"
                    start_text = start.strftime("%a %d %b, %H:%M %Z")
                    details = [
                        f"**{summary}**",
                        f"Venue: {name}",
                        f"Starts: {start_text}",
                        "Reminder: this event starts within the next 24 hours.",
                    ]
                    if event.get("url"):
                        details.append(f"[Event details]({event['url']})")
                    persistent_notification.async_create(
                        hass,
                        "\n\n".join(details),
                        title=f"UKGA event tomorrow — {name}",
                        notification_id=f"ukga_reminder_{reminder_key.split(':', 1)[1][:24]}",
                    )
                    processed_event_keys.add(reminder_key)
            if processed_event_keys:
                await favourite_store.async_mark_events_notified(processed_event_keys)
            return data
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
        hass.data[DOMAIN].pop(entry.entry_id + "_favourites", None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
