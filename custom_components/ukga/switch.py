"""Per-venue favourite switches."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .favourites import venue_key


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
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_favourite"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            via_device=(DOMAIN, entry_id),
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


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up one favourite switch per sauna."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    favourite_store = hass.data[DOMAIN][entry.entry_id + "_favourites"]
    venues = (coordinator.data or {}).get("venues", [])
    async_add_entities([
        UKGAVenueFavouriteSwitch(coordinator, entry.entry_id, venue, index, favourite_store)
        for index, venue in enumerate(venues)
    ])
