"""UI configuration flow."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN, DEFAULT_SOURCES


class UKGAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            source = user_input["gaysaunas"].strip()
            if not source.startswith("https://"):
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_url"},
                )
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="UK Gay Saunas & Events",
                data={"sources": [source]},
            )
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema(values=None):
        values = values or {}
        default_source = DEFAULT_SOURCES[0] if DEFAULT_SOURCES else "https://gaysaunas.co.uk/uk/england/"
        return vol.Schema({
            vol.Required("gaysaunas", default=values.get("gaysaunas", default_source)): str,
        })
