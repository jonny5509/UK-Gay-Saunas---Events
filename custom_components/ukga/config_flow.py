"""UI configuration flow for the source webpages."""
from __future__ import annotations

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN, DEFAULT_SOURCES


def _parse_sources(user_input):
    """Collect up to 15 optional webpage URLs and validate each one."""
    sources = []
    for index in range(1, 16):
        value = str(user_input.get(f"source_{index}", "") or "").strip()
        if not value:
            continue
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise vol.Invalid(f"Not a valid HTTPS URL: {value}")
        if value not in sources:
            sources.append(value)
    if not sources:
        raise vol.Invalid("Enter at least one source URL.")
    return sources


class UKGAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                sources = _parse_sources(user_input)
            except vol.Invalid:
                errors["base"] = "invalid_sources"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="UK Gay Saunas & Events",
                    data={"sources": sources},
                )

        schema = {}
        for index in range(1, 16):
            default = DEFAULT_SOURCES[index - 1] if index <= len(DEFAULT_SOURCES) else ""
            schema[vol.Optional(
                f"source_{index}",
                default=default,
            )] = selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "source_help": "Enter up to 15 HTTPS webpage URLs. Leave unused boxes blank."
            },
        )
