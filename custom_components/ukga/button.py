"""One information-notification button per sauna."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .favourites import venue_key, venue_id
from .sensor import _event_matches_venue, _event_start


class UKGAVenueInformationButton(CoordinatorEntity, ButtonEntity):
    """Create a notification containing information for one sauna."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name") or "Sauna"
        slug = "".join(c for c in name.lower() if c.isalnum()) or "sauna"
        self._attr_name = f"{name} information"
        self._attr_unique_id = f"{entry_id}_{venue_id(venue)}_information"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{venue_id(venue)}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    async def async_press(self):
        venue = self._venue
        data = self.coordinator.data or {}
        name = venue.get("name") or "Unnamed sauna"
        sections = [f"# {name}"]

        venue_url = venue.get("official_website") or venue.get("url")
        if venue_url:
            sections.extend(["", f"[Open venue page]({venue_url})", venue_url])

        now = datetime.now().astimezone()
        upcoming = []
        for event in data.get("events", []):
            start = _event_start(event)
            if start and start >= now and _event_matches_venue(event, venue):
                upcoming.append((start, event))
        upcoming.sort(key=lambda item: item[0])

        sections.extend(["", "## Upcoming events"])
        if not upcoming:
            sections.append("No matched upcoming events found.")
        for start, event in upcoming:
            sections.append(f"- **{event.get('summary') or 'Untitled event'}** — {start.strftime('%Y-%m-%d %H:%M %Z')}")
            if event.get("end"):
                sections.append(f"  - Ends: {event['end']}")
            if event.get("location"):
                sections.append(f"  - Location: {event['location']}")
            if event.get("url"):
                sections.append(f"  - [Event details]({event['url']})")
                sections.append(f"    {event['url']}")

        notification_id = f"ukga_sauna_{self._attr_unique_id}"
        persistent_notification.async_create(
            self.hass,
            "\n".join(sections),
            title=f"UKGA — {name}",
            notification_id=notification_id,
        )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up information buttons, including venues discovered on later refreshes."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    venues = (coordinator.data or {}).get("venues", [])
    known = {venue_key(venue) for venue in venues}
    async_add_entities([
        UKGAVenueInformationButton(coordinator, entry.entry_id, venue, index)
        for index, venue in enumerate(venues)
    ])

    def _add_new_venues():
        new_entities = []
        for index, venue in enumerate((coordinator.data or {}).get("venues", [])):
            key = venue_key(venue)
            if key in known:
                continue
            known.add(key)
            new_entities.append(UKGAVenueInformationButton(coordinator, entry.entry_id, venue, index))
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_add_new_venues))
