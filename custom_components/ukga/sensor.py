"""Summary and upcoming-event sensors."""
from __future__ import annotations

from datetime import datetime
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
    """Expose the next scraped event as a readable sensor."""

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


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        UKGASummarySensor(coordinator, entry.entry_id),
        UKGANextEventSensor(coordinator, entry.entry_id),
    ])
