"""Single button to notify all venue information and upcoming events."""
from __future__ import annotations

from urllib.parse import quote_plus

from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .sensor import _event_matches_venue, _event_start


class UKGAAllInformationButton(CoordinatorEntity, ButtonEntity):
    """Create one persistent notification with all scraped venue information."""

    _attr_has_entity_name = True
    _attr_name = "Notify all sauna information"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_all_information_notification"

    async def async_press(self):
        data = self.coordinator.data or {}
        venues = data.get("venues", [])
        events = data.get("events", [])
        now = __import__("datetime").datetime.now().astimezone()
        sections = ["# UKGA — All sauna information", f"Venues found: {len(venues)}", ""]

        for venue in venues:
            name = venue.get("name") or "Unnamed venue"
            address = venue.get("address") or "Address not available"
            website = venue.get("official_website") or venue.get("url") or ""
            map_query = venue.get("address") or name
            sections.extend([
                f"## {name}",
                f"- **Address:** {address}",
                f"- **Website:** {website}" if website else "- **Website:** Not available",
                f"- **Map:** https://www.google.com/maps/search/?api=1&query={quote_plus(map_query)}",
            ])
            description = venue.get("description")
            if description:
                sections.append(f"- **Description:** {description}")
            source_url = venue.get("url")
            if source_url:
                sections.append(f"- **Source:** {source_url}")
            source_directory = venue.get("source_directory")
            if source_directory:
                sections.append(f"- **Directory:** {source_directory}")
            for source_link in venue.get("source_links") or []:
                if source_link and source_link not in (source_url, website):
                    sections.append(f"- **Additional link:** {source_link}")

            upcoming = []
            for event in events:
                start = _event_start(event)
                if start and start >= now and _event_matches_venue(event, venue):
                    upcoming.append((start, event))
            upcoming.sort(key=lambda item: item[0])
            if upcoming:
                sections.append("- **Upcoming events:**")
                for start, event in upcoming:
                    title = event.get("summary") or "Untitled event"
                    event_details = [f"  - **{title}** — {start.strftime('%Y-%m-%d %H:%M %Z')}"]
                    if event.get("end"):
                        event_details.append(f" (ends {event.get('end')})")
                    sections.append("".join(event_details))
                    if event.get("location"):
                        sections.append(f"    - Location: {event.get('location')}")
                    if event.get("description"):
                        sections.append(f"    - Details: {event.get('description')}")
                    if event.get("url"):
                        sections.append(f"    - Link: {event.get('url')}")
            else:
                sections.append("- **Upcoming events:** No matched upcoming events found")
            sections.append("")

        if data.get("source_errors"):
            sections.extend(["## Scraper warnings"])
            sections.extend(f"- {error}" for error in data["source_errors"])
            sections.append("")

        persistent_notification.async_create(
            self.hass,
            "\n".join(sections),
            title="UKGA — All sauna information",
            notification_id="ukga_all_sauna_information",
        )


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the single all-information notification button."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UKGAAllInformationButton(coordinator, entry.entry_id)])
