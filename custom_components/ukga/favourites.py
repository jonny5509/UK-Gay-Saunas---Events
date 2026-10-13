"""Persistent favourite venues for UKGA."""
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
    """Store favourite venue keys in Home Assistant's storage."""

    def __init__(self, hass, entry_id: str) -> None:
        self._store = Store(hass, 1, f"{DOMAIN}_{entry_id}_favourites")
        self.favourites: set[str] = set()

    async def async_load(self) -> None:
        """Load persisted favourites."""
        data = await self._store.async_load() or {}
        self.favourites = {
            str(key) for key in data.get("favourites", [])
            if isinstance(key, str)
        }

    def is_favourite(self, venue: dict) -> bool:
        return venue_key(venue) in self.favourites

    async def async_set_favourite(self, venue: dict, favourite: bool) -> None:
        """Update and persist a venue favourite."""
        key = venue_key(venue)
        if favourite:
            self.favourites.add(key)
        else:
            self.favourites.discard(key)
        await self._store.async_save({"favourites": sorted(self.favourites)})
