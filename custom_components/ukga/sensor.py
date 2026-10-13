"""Summary and upcoming-event sensors."""
from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urlparse

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def _event_start(event):
    value = event.get("start")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return parsed
    except (TypeError, ValueError):
        return None


def _normalise(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _event_matches_venue(event, venue):
    """Match events to a venue using names, locations, and known venue URLs."""
    venue_name = _normalise(venue.get("name"))
    location = _normalise(event.get("location"))
    if venue_name and location and (
        venue_name in location or (len(location) >= 8 and location in venue_name)
    ):
        return True

    event_url = str(event.get("url") or "").rstrip("/")
    if event_url:
        known_urls = [
            venue.get("url", ""),
            venue.get("official_website", ""),
            *(venue.get("source_links") or []),
        ]
        event_parsed = urlparse(event_url)
        for known_url in known_urls:
            if not known_url:
                continue
            known = str(known_url).rstrip("/")
            if event_url == known:
                return True
            known_parsed = urlparse(known)
            # Match a page on the same host only when the known URL is a
            # specific venue page, not a shared directory homepage.
            if (
                known_parsed.netloc
                and known_parsed.netloc == event_parsed.netloc
                and known_parsed.path not in ("", "/")
                and event_parsed.path.startswith(known_parsed.path.rstrip("/") + "/")
            ):
                return True
    return False


class UKGASummarySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Venue count"
    _attr_icon = "mdi:sauna"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_venue_count"

    @property
    def native_value(self):
        return len((self.coordinator.data or {}).get("venues", []))

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "event_count": len(data.get("events", [])),
            "last_updated": data.get("last_updated"),
            "source_errors": data.get("source_errors", []),
            "sources": data.get("sources", []),
        }


class UKGANextEventSensor(CoordinatorEntity, SensorEntity):
    """Expose the next scraped event across all venues."""

    _attr_has_entity_name = True
    _attr_name = "Next event"
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_next_event"

    @property
    def _next_event(self):
        now = datetime.now().astimezone()
        upcoming = []
        for event in (self.coordinator.data or {}).get("events", []):
            start = _event_start(event)
            if start and start >= now:
                upcoming.append((start, event))
        return min(upcoming, key=lambda item: item[0])[1] if upcoming else None

    @property
    def native_value(self):
        event = self._next_event
        return event.get("summary") if event else "No upcoming events"

    @property
    def extra_state_attributes(self):
        event = self._next_event
        if not event:
            return {"event_count": 0}
        return {
            "start": event.get("start"),
            "end": event.get("end"),
            "location": event.get("location"),
            "description": event.get("description"),
            "url": event.get("url"),
        }


class UKGAVenueNextEventSensor(CoordinatorEntity, SensorEntity):
    """Expose the next event matched to an individual venue."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name", "Venue")
        slug = _normalise(name) or "venue"
        self._attr_name = f"{name} next event"
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_next_event"

    @property
    def _upcoming_events(self):
        now = datetime.now().astimezone()
        events = []
        for event in (self.coordinator.data or {}).get("events", []):
            start = _event_start(event)
            if start and start >= now and _event_matches_venue(event, self._venue):
                events.append((start, event))
        return sorted(events, key=lambda item: item[0])

    @property
    def native_value(self):
        events = self._upcoming_events
        return events[0][1].get("summary") if events else "No upcoming events"

    @property
    def extra_state_attributes(self):
        events = self._upcoming_events
        if not events:
            return {"venue": self._venue.get("name"), "upcoming_event_count": 0}
        event = events[0][1]
        return {
            "venue": self._venue.get("name"),
            "start": event.get("start"),
            "end": event.get("end"),
            "location": event.get("location"),
            "description": event.get("description"),
            "url": event.get("url"),
            "upcoming_event_count": len(events),
        }


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    venues = (coordinator.data or {}).get("venues", [])
    async_add_entities([
        UKGASummarySensor(coordinator, entry.entry_id),
        UKGANextEventSensor(coordinator, entry.entry_id),
        *[
            UKGAVenueNextEventSensor(coordinator, entry.entry_id, venue, index)
            for index, venue in enumerate(venues)
        ],
    ])
