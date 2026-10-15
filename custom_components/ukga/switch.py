"""Per-venue favourite switches."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .favourites import venue_key, venue_id


class UKGAVenueFavouriteSwitch(CoordinatorEntity, SwitchEntity):
    """Toggle whether a venue is saved as a favourite."""

    _attr_has_entity_name = True
    _attr_name = "Favourite"
    _attr_icon = "mdi:heart"

    def __init__(self, coordinator, entry_id, venue, index, favourite_store):
        super().__init__(coordinator)
        self._venue = venue
        self._favourite_store = favourite_store
        name = venue.get("name") or "Sauna"
        slug = "".join(char for char in name.lower() if char.isalnum()) or "sauna"
        self._attr_unique_id = f"{entry_id}_{venue_id(venue)}_favourite"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{venue_id(venue)}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    @property
    def is_on(self):
        return self._favourite_store.is_favourite(self._current_venue)

    @property
    def _current_venue(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        key = venue_key(self._venue)
        return next((venue for venue in venues if venue_key(venue) == key), self._venue)

    @property
    def extra_state_attributes(self):
        venue = self._current_venue
        return {
            "venue": venue.get("name"),
            "directory_url": venue.get("url"),
            "official_website": venue.get("official_website"),
        }

    async def async_turn_on(self, **kwargs):
        await self._favourite_store.async_set_favourite(self._current_venue, True)
        self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs):
        await self._favourite_store.async_set_favourite(self._current_venue, False)
        self.coordinator.async_update_listeners()


class UKGAVenueNotificationsSwitch(UKGAVenueFavouriteSwitch):
    """Toggle event notifications for a venue."""

    _attr_name = "Notifications"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry_id, venue, index, favourite_store):
        super().__init__(coordinator, entry_id, venue, index, favourite_store)
        name = venue.get("name") or "Sauna"
        slug = "".join(char for char in name.lower() if char.isalnum()) or "sauna"
        self._attr_unique_id = f"{entry_id}_{venue_id(venue)}_notifications"

    @property
    def is_on(self):
        return self._favourite_store.notifications_enabled(self._current_venue)

    async def async_turn_on(self, **kwargs):
        await self._favourite_store.async_set_notifications(self._current_venue, True)
        self.coordinator.async_update_listeners()

    async def async_turn_off(self, **kwargs):
        await self._favourite_store.async_set_notifications(self._current_venue, False)
        self.coordinator.async_update_listeners()


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up per-venue switches, including venues found after initial setup."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    favourite_store = hass.data[DOMAIN][entry.entry_id + "_favourites"]
    venues = (coordinator.data or {}).get("venues", [])
    known = {venue_key(venue) for venue in venues}
    async_add_entities([
        entity
        for index, venue in enumerate(venues)
        for entity in (
            UKGAVenueFavouriteSwitch(coordinator, entry.entry_id, venue, index, favourite_store),
            UKGAVenueNotificationsSwitch(coordinator, entry.entry_id, venue, index, favourite_store),
        )
    ])

    def _add_new_venues():
        new_entities = []
        for index, venue in enumerate((coordinator.data or {}).get("venues", [])):
            key = venue_key(venue)
            if key in known:
                continue
            known.add(key)
            new_entities.extend((
                UKGAVenueFavouriteSwitch(coordinator, entry.entry_id, venue, index, favourite_store),
                UKGAVenueNotificationsSwitch(coordinator, entry.entry_id, venue, index, favourite_store),
            ))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_venues))
