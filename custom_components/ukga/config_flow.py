"""UI configuration flow for the source directories."""
from __future__ import annotations

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import DOMAIN, DEFAULT_SOURCES


def _parse_sources(value):
    """Parse newline-separated source URLs and reject malformed input."""
    sources = list(dict.fromkeys(
        line.strip() for line in str(value or "").splitlines() if line.strip()
    ))
    if not sources:
        raise vol.Invalid("Enter at least one source URL.")
    for source in sources:
        parsed = urlparse(source)
        if parsed.scheme != "https" or not parsed.netloc:
            raise vol.Invalid(f"Not a valid HTTPS URL: {source}")
    return sources


class UKGAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                sources = _parse_sources(user_input["sources"])
            except vol.Invalid:
                errors["sources"] = "invalid_sources"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="UK Gay Saunas & Events",
                    data={"sources": sources},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("sources", default="\n".join(DEFAULT_SOURCES)): selector.TextSelector(\n                    selector.TextSelectorConfig(multiline=True)\n                ),
            }),
            errors=errors,
            description_placeholders={
                "source_help": "Enter one HTTPS directory URL per line."
            },
        )
