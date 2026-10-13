"""UI configuration flow."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, DEFAULT_SOURCES

class UKGAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            sources = [
                user_input["misterbandb"].strip(),
                user_input["gaysaunas"].strip(),
            ]
            if not all(url.startswith("https://") for url in sources):
                return self.async_show_form(
                    step_id="user", data_schema=self._schema(user_input),
                    errors={"base": "invalid_url"},
                )
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="UK Gay Saunas & Events", data={"sources": sources}
            )
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema(values=None):
        values = values or {}
        return vol.Schema({
            vol.Required("misterbandb", default=values.get("misterbandb", DEFAULT_SOURCES[0])): str,
            vol.Required("gaysaunas", default=values.get("gaysaunas", DEFAULT_SOURCES[1])): str,
        })
