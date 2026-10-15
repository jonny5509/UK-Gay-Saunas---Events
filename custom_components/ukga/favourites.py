"""Persistent favourites and venue notification preferences for UKGA."""
from __future__ import annotations

import hashlib

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN


def venue_key(venue: dict) -> str:
    """Return a stable key for a venue across directory refreshes."""
    url = str(venue.get("url") or "").strip().rstrip("/")
    if url:
        return url.lower()
    name = str(venue.get("name") or "unknown").strip().lower()
    return f"name:{name}"


def venue_id(venue: dict) -> str:
    """Return a compact, stable identifier independent of directory ordering."""
    return hashlib.sha256(venue_key(venue).encode("utf-8")).hexdigest()[:16]


def migrate_legacy_venue_entities(hass, entry, venues, platform, suffixes) -> None:
    """Migrate index-based entity/device identifiers without orphaning existing entities."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    for venue in venues:
        name = str(venue.get("name") or "sauna")
        slug = "".join(char for char in name.lower() if char.isalnum()) or "sauna"
        stable_id = venue_id(venue)
        for suffix in suffixes:
            new_unique_id = f"{entry.entry_id}_{stable_id}_{suffix}"
            if entity_registry.async_get_entity_id(platform, DOMAIN, new_unique_id):
                continue
            legacy = [
                entity for entity in entity_registry.entities.values()
                if entity.config_entry_id == entry.entry_id
                and entity.platform == platform
                and entity.unique_id.endswith(f"_{slug}_{suffix}")
                and entity.unique_id != new_unique_id
            ]
            if len(legacy) == 1:
                entity_registry.async_update_entity(
                    legacy[0].entity_id, new_unique_id=new_unique_id
                )

        stable_identifier = (DOMAIN, f"{entry.entry_id}_sauna_{stable_id}")
        if any(stable_identifier in device.identifiers for device in device_registry.devices.values()):
            continue
        legacy_devices = []
        prefix = f"{entry.entry_id}_sauna_"
        for device in device_registry.devices.values():
            if entry.entry_id not in device.config_entries:
                continue
            for domain, identifier in device.identifiers:
                if domain != DOMAIN or not identifier.startswith(prefix):
                    continue
                tail = identifier[len(prefix):]
                old_slug = tail.rsplit("_", 1)[-1]
                old_index = tail.split("_", 1)[0]
                if old_index.isdigit() and old_slug == slug:
                    legacy_devices.append(device)
                    break
        if len(legacy_devices) == 1:
            device_registry.async_update_device(
                legacy_devices[0].id, new_identifiers={stable_identifier}
            )


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
