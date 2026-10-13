"""One information-notification button per sauna."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote_plus

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
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
        self._attr_name = f"{name} information"
        self._attr_unique_id = f"{entry_id}_{index}_{name.lower().replace(' ', '_')}_information"

    async def async_press(self):
        venue = self._venue
        data = self.coordinator.data or {}
        name = venue.get("name") or "Unnamed sauna"
        address = venue.get("address") or "Address not available"
        website = venue.get("official_website") or venue.get("url") or ""
        map_query = venue.get("address") or name
        sections = [
            f"# {name}",
            f"- **Address:** {address}",
            f"- **Website:** {website or 'Not available'}",
            f"- **Map:** https://www.google.com/maps/search/?api=1&query={quote_plus(map_query)}",
        ]
        if venue.get("description"):
            sections.append(f"- **Description:** {venue['description']}")
        if venue.get("url"):
            sections.append(f"- **Source:** {venue['url']}")
        if venue.get("source_directory"):
            sections.append(f"- **Directory:** {venue['source_directory']}")
        for link in venue.get("source_links") or []:
            if link and link not in (venue.get("url"), website):
                sections.append(f"- **Additional link:** {link}")

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
