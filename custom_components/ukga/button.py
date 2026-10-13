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
        slug = "".join(
            c.lower() if c.isalnum() else "_" for c in venue.get("name", "venue")
        ).strip("_")
        self._attr_unique_id = f"{index}_{slug}_address"
        self._attr_name = f"{venue.get('name', 'Venue')} — Get address"
        address = venue.get("address") or ""
        query = address if address else venue.get("name", "")
        self._attr_extra_state_attributes = {
            "address": address or "Not extracted; Maps searches venue name",
            "google_maps_url": "https://www.google.com/maps/search/?api=1&query="
            + quote_plus(query),
            "official_website": venue.get("official_website", ""),
            "description": venue.get("description", ""),
            "source_url": venue.get("url", ""),
            "source_directory": venue.get("source_directory", ""),
            "source_links": venue.get("source_links", []),
        }

    async def async_press(self):
        # HA button entities cannot open a browser URL directly. Use the
        # google_maps_url attribute in a Lovelace card's URL tap action.
        return


class VenueWebsiteButton(CoordinatorEntity, ButtonEntity):
    """Expose a per-venue website button and its URL for dashboard navigation."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:web"

    def __init__(self, coordinator, venue, index):
        super().__init__(coordinator)
        name = venue.get("name", "Venue")
        slug = "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")
        website = venue.get("official_website") or venue.get("url") or ""
        self._attr_unique_id = f"{index}_{slug}_website"
        self._attr_name = f"{name} — Website"
        self._attr_extra_state_attributes = {
            "website_url": website,
            "venue": name,
            "source_url": venue.get("url", ""),
        }

    async def async_press(self):
        # Home Assistant button entities cannot launch a browser URL on press.
        # The website_url attribute can be used by a Lovelace card's URL action.
        return


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    venues = (coordinator.data or {}).get("venues", [])
    entities = []
    for index, venue in enumerate(venues):
        entities.append(VenueAddressButton(coordinator, venue, index))
        entities.append(VenueWebsiteButton(coordinator, venue, index))
    async_add_entities(entities)
