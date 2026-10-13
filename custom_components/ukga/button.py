"""Venue buttons expose map, official website, and source links."""
from __future__ import annotations

from urllib.parse import quote_plus
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class VenueAddressButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker"

    def __init__(self, coordinator, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        slug = "".join(c.lower() if c.isalnum() else "_" for c in venue.get("name", "venue")).strip("_")
        self._attr_unique_id = f"{index}_{slug}_address"
        self._attr_name = f"{venue.get('name', 'Venue')} — Get address"
        address = venue.get("address") or ""
        query = address if address else venue.get("name", "")
        self._attr_extra_state_attributes = {
            "address": address or "Not extracted; Maps searches venue name",
            "google_maps_url": "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query),
            "official_website": venue.get("official_website", ""),
            "description": venue.get("description", ""),
            "source_url": venue.get("url", ""),
            "source_directory": venue.get("source_directory", ""),
            "source_links": venue.get("source_links", []),
        }

    async def async_press(self):
        # HA button entities do not open URLs themselves; attributes can be used
        # in a Lovelace button-card tap_action.
        return

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        VenueAddressButton(coordinator, venue, index)
        for index, venue in enumerate((coordinator.data or {}).get("venues", []))
    ])
