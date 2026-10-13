"""Per-sauna upcoming-event sensors."""
from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import urlparse

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .favourites import venue_key


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

def _safe_state_text(value, limit=250):
    """Keep text sensor states within Home Assistant's 255-character limit."""
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text or "Unknown"


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
            if (
                known_parsed.netloc
                and known_parsed.netloc == event_parsed.netloc
                and known_parsed.path not in ("", "/")
                and event_parsed.path.startswith(known_parsed.path.rstrip("/") + "/")
            ):
                return True
    return False


class UKGACrawlSummarySensor(CoordinatorEntity, SensorEntity):
    """Expose per-region crawl counts to help verify directory coverage."""

    _attr_has_entity_name = False
    _attr_name = "UKGA directory crawl"
    _attr_icon = "mdi:database-search"
    _attr_native_unit_of_measurement = "venues"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_directory_crawl_summary"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="UKGA Sauna Hub",
            manufacturer="UK Gay Saunas & Events",
            model="Sauna directory and events hub",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return len(data.get("venues", []))

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "regions": data.get("source_stats", []),
            "source_errors": data.get("source_errors", []),
            "total_pages_visited": sum(
                item.get("pages_visited", 0) for item in data.get("source_stats", [])
            ),
            "total_events_found": len(data.get("events", [])),
            "last_updated": data.get("last_updated"),
        }


class UKGAVenueNextEventSensor(CoordinatorEntity, SensorEntity):
    """Expose the next event matched to an individual sauna."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:calendar-star"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name") or "Sauna"
        slug = _normalise(name) or "sauna"
        self._attr_name = f"{name} next event"
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_next_event"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

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
        return _safe_state_text(events[0][1].get("summary")) if events else "No upcoming events"

    @property
    def extra_state_attributes(self):
        events = self._upcoming_events
        if not events:
            return {"sauna": self._venue.get("name"), "upcoming_event_count": 0}
        event = events[0][1]
        return {
            "sauna": self._venue.get("name"),
            "start": event.get("start"),
            "end": event.get("end"),
            "location": event.get("location"),
            "description": event.get("description"),
            "url": event.get("url"),
            "upcoming_event_count": len(events),
        }



class UKGAVenueOpeningStatusSensor(CoordinatorEntity, SensorEntity):
    """Report Open/Closed only when published opening hours are available."""

    _attr_has_entity_name = True
    _attr_name = "Opening status"
    _attr_icon = "mdi:help-circle-outline"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name") or "Sauna"
        slug = _normalise(name) or "sauna"
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_opening_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    @property
    def _current_venue(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        return next(
            (venue for venue in venues
             if venue.get("url") == self._venue.get("url")
             or venue.get("name") == self._venue.get("name")),
            self._venue,
        )

    @staticmethod
    def _minutes(value):
        try:
            hour, minute = str(value).split(":", 1)
            hour, minute = int(hour), int(minute)
            if minute not in range(60) or hour not in range(25) or (hour == 24 and minute != 0):
                return None
            return hour * 60 + minute
        except (TypeError, ValueError):
            return None

    @property
    def _schedule(self):
        value = self._current_venue.get("opening_hours")
        if not isinstance(value, dict):
            return None
        schedule = {}
        for day, ranges in value.items():
            if not isinstance(ranges, list):
                continue
            parsed = []
            for interval in ranges:
                if not isinstance(interval, (list, tuple)) or len(interval) != 2:
                    continue
                start, end = self._minutes(interval[0]), self._minutes(interval[1])
                if start is not None and end is not None and start != end:
                    parsed.append((start, end))
            schedule[str(day).lower()] = parsed
        return schedule if any(schedule.values()) else None

    @property
    def native_value(self):
        from homeassistant.util import dt as dt_util

        schedule = self._schedule
        if not schedule:
            return "Unknown"
        now = dt_util.now()
        day_names = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        today = day_names[now.weekday()]
        yesterday = day_names[(now.weekday() - 1) % 7]
        minute = now.hour * 60 + now.minute

        for start, end in schedule.get(today, []):
            if (start < end and start <= minute < end) or (start > end and minute >= start):
                return "Open"
        # An overnight opening period belongs to the previous day's schedule.
        for start, end in schedule.get(yesterday, []):
            if start > end and minute < end:
                return "Open"
        return "Closed"

    @property
    def icon(self):
        value = self.native_value
        return {
            "Open": "mdi:door-open",
            "Closed": "mdi:door-closed",
            "Unknown": "mdi:help-circle-outline",
        }.get(value, "mdi:help-circle-outline")

    @property
    def extra_state_attributes(self):
        return {
            "sauna": self._current_venue.get("name"),
            "published_opening_hours": self._schedule,
            "source_url": self._current_venue.get("opening_hours_source_url") or self._current_venue.get("url"),
            "information_source": self._current_venue.get("opening_hours_source", "directory"),
            "status_basis": "Published opening hours; not event listings",
        }



class UKGAVenuePricingSensor(CoordinatorEntity, SensorEntity):
    """Show venue pricing when explicitly published on the directory page."""

    _attr_has_entity_name = True
    _attr_name = "Pricing"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name") or "Sauna"
        slug = _normalise(name) or "sauna"
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_pricing"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    @property
    def _current_venue(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        return next(
            (venue for venue in venues
             if venue.get("url") == self._venue.get("url")
             or venue.get("name") == self._venue.get("name")),
            self._venue,
        )

    @property
    def native_value(self):
        return _safe_state_text(self._current_venue.get("pricing"), 250) if self._current_venue.get("pricing") else "Not published"

    @property
    def extra_state_attributes(self):
        return {
            "sauna": self._current_venue.get("name"),
            "source_url": self._current_venue.get("pricing_source_url") or self._current_venue.get("url"),
            "information_source": self._current_venue.get("pricing_source", "directory"),
            "pricing_basis": "Official website preferred; directory information used when no official price is found",
        }



class UKGAVenuePrivateRoomsSensor(CoordinatorEntity, SensorEntity):
    """Report whether private rooms are explicitly advertised."""

    _attr_has_entity_name = True
    _attr_name = "Private rooms"
    _attr_icon = "mdi:door-closed-lock"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name") or "Sauna"
        slug = _normalise(name) or "sauna"
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_private_rooms"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    @property
    def _current_venue(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        return next(
            (venue for venue in venues
             if venue.get("url") == self._venue.get("url")
             or venue.get("name") == self._venue.get("name")),
            self._venue,
        )

    @property
    def native_value(self):
        return _safe_state_text(self._current_venue.get("private_rooms"), 250) if self._current_venue.get("private_rooms") else "Not specified"

    @property
    def extra_state_attributes(self):
        return {
            "sauna": self._current_venue.get("name"),
            "source_url": self._current_venue.get("private_rooms_source_url") or self._current_venue.get("url"),
            "information_source": self._current_venue.get("private_rooms_source", "directory"),
            "status_basis": "Explicit private-room wording; official website preferred, directory used as fallback; absence of information is Unknown",
        }


class UKGAVenueWebsiteSensor(CoordinatorEntity, SensorEntity):
    """Expose the researched official website for a venue."""

    _attr_has_entity_name = True
    _attr_name = "Official website"
    _attr_icon = "mdi:web"

    def __init__(self, coordinator, entry_id, venue, index):
        super().__init__(coordinator)
        self._venue = venue
        name = venue.get("name") or "Sauna"
        slug = _normalise(name) or "sauna"
        self._attr_unique_id = f"{entry_id}_{index}_{slug}_official_website"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sauna_{index}_{slug}")},
            name=name,
            manufacturer="UK Gay Saunas & Events",
            configuration_url=venue.get("official_website") or venue.get("url"),
        )

    @property
    def _current_venue(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        return next(
            (venue for venue in venues
             if venue.get("url") == self._venue.get("url")
             or venue.get("name") == self._venue.get("name")),
            self._venue,
        )

    @property
    def native_value(self):
        return _safe_state_text(self._current_venue.get("official_website"), 250) if self._current_venue.get("official_website") else "Not found"

    @property
    def extra_state_attributes(self):
        venue = self._current_venue
        return {
            "sauna": venue.get("name"),
            "directory_url": venue.get("url"),
            "match_status": venue.get("website_match_status") or "Not found",
        }


class UKGAFavouritesSensor(CoordinatorEntity, SensorEntity):
    """List saved favourite venues."""

    _attr_has_entity_name = False
    _attr_name = "UKGA favourites"
    _attr_icon = "mdi:heart-multiple"

    def __init__(self, coordinator, entry_id, favourite_store):
        super().__init__(coordinator)
        self._favourite_store = favourite_store
        self._attr_unique_id = f"{entry_id}_favourites"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="UKGA Sauna Hub",
            manufacturer="UK Gay Saunas & Events",
            model="Sauna directory and events hub",
        )

    @property
    def _favourite_venues(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        return [
            venue for venue in venues
            if self._favourite_store.is_favourite(venue)
        ]

    @property
    def native_value(self):
        return len(self._favourite_venues)

    @property
    def extra_state_attributes(self):
        return {
            "favourites": [
                {
                    "name": venue.get("name"),
                    "directory_url": venue.get("url"),
                    "official_website": venue.get("official_website"),
                }
                for venue in self._favourite_venues
            ],
        }


class UKGANotificationSubscriptionsSensor(CoordinatorEntity, SensorEntity):
    """List venues whose event notifications are enabled."""

    _attr_has_entity_name = False
    _attr_name = "UKGA notification subscriptions"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry_id, favourite_store):
        super().__init__(coordinator)
        self._favourite_store = favourite_store
        self._attr_unique_id = f"{entry_id}_notification_subscriptions"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="UKGA Sauna Hub",
            manufacturer="UK Gay Saunas & Events",
            model="Sauna directory and events hub",
        )

    @property
    def _subscribed_venues(self):
        venues = (self.coordinator.data or {}).get("venues", [])
        return [
            venue for venue in venues
            if self._favourite_store.notifications_enabled(venue)
        ]

    @property
    def native_value(self):
        return len(self._subscribed_venues)

    @property
    def extra_state_attributes(self):
        return {
            "notification_subscriptions": [
                {
                    "name": venue.get("name"),
                    "directory_url": venue.get("url"),
                    "official_website": venue.get("official_website"),
                }
                for venue in self._subscribed_venues
            ],
            "notification_type": "Newly discovered upcoming events",
        }


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    venues = (coordinator.data or {}).get("venues", [])
    favourite_store = hass.data[DOMAIN][entry.entry_id + "_favourites"]
    async_add_entities([
        UKGACrawlSummarySensor(coordinator, entry.entry_id),
        UKGAFavouritesSensor(coordinator, entry.entry_id, favourite_store),
        UKGANotificationSubscriptionsSensor(coordinator, entry.entry_id, favourite_store),
        *[
            entity
            for index, venue in enumerate(venues)
            for entity in (
                UKGAVenueNextEventSensor(coordinator, entry.entry_id, venue, index),
                UKGAVenueOpeningStatusSensor(coordinator, entry.entry_id, venue, index),
                UKGAVenuePricingSensor(coordinator, entry.entry_id, venue, index),
                UKGAVenuePrivateRoomsSensor(coordinator, entry.entry_id, venue, index),
                UKGAVenueWebsiteSensor(coordinator, entry.entry_id, venue, index),
            )
        ],
    ])
