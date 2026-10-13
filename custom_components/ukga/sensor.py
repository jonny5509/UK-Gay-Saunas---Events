"""Summary sensors for scrape status."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

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

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UKGASummarySensor(coordinator, entry.entry_id)])
