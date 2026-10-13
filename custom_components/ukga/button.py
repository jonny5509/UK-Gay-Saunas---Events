"""One information-notification button per sauna."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
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
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_information"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            via_device=(DOMAIN, entry_id),
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    async def async_press(self):
        venue = self._venue
        data = self.coordinator.data or {}
        name = venue.get("name") or "Unnamed sauna"
        sections = [f"# {name}"]
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
            if event.get("description"):
                sections.append(f"  - Details: {event['description']}")
            if event.get("url"):
                sections.append(f"  - Link: {event['url']}")

        notification_id = f"ukga_sauna_{self._attr_unique_id}"
        persistent_notification.async_create(
            self.hass,
            "\n".join(sections),
            title=f"UKGA — {name}",
            notification_id=notification_id,
        )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up one information button for each sauna."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    venues = (coordinator.data or {}).get("venues", [])
    async_add_entities([
        UKGAVenueInformationButton(coordinator, entry.entry_id, venue, index)
        for index, venue in enumerate(venues)
    ])
