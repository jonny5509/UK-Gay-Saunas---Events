"""Persistent favourites and venue notification preferences for UKGA."""
from __future__ import annotations

from homeassistant.helpers.storage import Store

from .const import DOMAIN


def venue_key(venue: dict) -> str:
    """Return a stable key for a venue across directory refreshes."""
    url = str(venue.get("url") or "").strip().rstrip("/")
    if url:
        return url.lower()
    name = str(venue.get("name") or "unknown").strip().lower()
    return f"name:{name}"


class FavouriteStore:
    """Store favourite venues and notification subscriptions."""

    def __init__(self, hass, entry_id: str) -> None:
        self._store = Store(hass, 1, f"{DOMAIN}_{entry_id}_favourites")
        self.favourites: set[str] = set()
        self.notification_venues: set[str] = set()
        self.notified_events: set[str] = set()
        self._loaded = False

    async def async_load(self) -> None:
        """Load persisted preferences."""
        data = await self._store.async_load() or {}
        self.favourites = {str(k) for k in data.get("favourites", []) if isinstance(k, str)}
        self.notification_venues = {
            str(k) for k in data.get("notification_venues", []) if isinstance(k, str)
        }
        self.notified_events = {
            str(k) for k in data.get("notified_events", []) if isinstance(k, str)
        }
        self._loaded = True

    def is_favourite(self, venue: dict) -> bool:
        return venue_key(venue) in self.favourites

    def notifications_enabled(self, venue: dict) -> bool:
        return venue_key(venue) in self.notification_venues

    async def async_set_favourite(self, venue: dict, favourite: bool) -> None:
        key = venue_key(venue)
        if favourite:
            self.favourites.add(key)
        else:
            self.favourites.discard(key)
        await self._async_save()

    async def async_set_notifications(self, venue: dict, enabled: bool) -> None:
        key = venue_key(venue)
        if enabled:
            self.notification_venues.add(key)
        else:
            self.notification_venues.discard(key)
        await self._async_save()

    async def async_mark_events_notified(self, event_keys) -> None:
        """Remember events so they cannot repeatedly trigger notifications."""
        self.notified_events.update(event_keys)
        # Keep storage bounded while preserving recent event fingerprints.
        self.notified_events = set(sorted(self.notified_events)[-1500:])
        await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save({
            "favourites": sorted(self.favourites),
            "notification_venues": sorted(self.notification_venues),
            "notified_events": sorted(self.notified_events),
        })
