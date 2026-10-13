"""UI configuration flow."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN, DEFAULT_SOURCES


class UKGAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="UK Gay Saunas & Events",
                data={"sources": list(DEFAULT_SOURCES)},
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )
