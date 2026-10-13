"""Clean, title-only Home Assistant calendar for UKGA events."""
from __future__ import annotations

from datetime import datetime
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from .const import DOMAIN


def _parse(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt_util.as_local(parsed)
    except (ValueError, TypeError):
        return None


def _calendar_event(item, start, end):
    # Keep calendar entries tidy: the event title is the only displayed text.
    title = " ".join(str(item.get("summary") or "Event").split())
    return CalendarEvent(summary=title, start=start, end=end, description="", location="")


class UKGAEventsCalendar(CoordinatorEntity, CalendarEntity):
    _attr_has_entity_name = True
    _attr_name = "Events"
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_events"

    @property
    def event(self):
        now = dt_util.now()
        events = []
        for item in (self.coordinator.data or {}).get("events", []):
            start, end = _parse(item.get("start")), _parse(item.get("end"))
            if start and end and end >= now:
                events.append((start, end, item))
        if not events:
            return None
        start, end, item = min(events, key=lambda row: row[0])
        return _calendar_event(item, start, end)

    async def async_get_events(self, hass, start_date, end_date):
        results = []
        for item in (self.coordinator.data or {}).get("events", []):
            start, end = _parse(item.get("start")), _parse(item.get("end"))
            if not start:
                continue
            if not end or end < start:
                end = start
            if start < end_date and end >= start_date:
                results.append(_calendar_event(item, start, end))
        return sorted(results, key=lambda item: item.start)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UKGAEventsCalendar(coordinator, entry.entry_id)])
