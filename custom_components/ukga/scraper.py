"""Best-effort directory and Schema.org Event scraper for the two configured sources.

The directory pages are not guaranteed to expose structured event data. This module
collects same-site venue links, then looks for Schema.org Event and address metadata
on a limited number of linked pages. Source HTML changes may require adjustments.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlparse

from .const import MAX_PAGES_PER_SOURCE

HEADERS = {"User-Agent": "Home Assistant UKGA integration/0.1 (personal use)"}
SKIP = ("privacy", "cookies", "contact", "about us", "terms", "login", "register", "facebook", "instagram")

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

class PageParser(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links = []
        self.anchor = None
        self.scripts = []
        self.in_script = False
        self.script_type = ""
        self.script_buf = []
        self.text = []
        self._title = False
        self.title_buf = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._title = True
        if tag == "a" and attrs.get("href"):
            self.anchor = {"url": urljoin(self.base, attrs["href"]), "text": []}
        if tag == "script":
            self.in_script = True
            self.script_type = attrs.get("type", "")
            self.script_buf = []

    def handle_data(self, data):
        value = clean(data)
        if value:
            self.text.append(value)
        if self._title:
            self.title_buf.append(value)
        if self.anchor is not None and value:
            self.anchor["text"].append(value)
        if self.in_script:
            self.script_buf.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self._title = False
        if tag == "a" and self.anchor is not None:
            label = clean(" ".join(self.anchor["text"]))
            if label:
                self.links.append({"url": self.anchor["url"], "name": label})
            self.anchor = None
        if tag == "script" and self.in_script:
            if "ld+json" in self.script_type.lower():
                self.scripts.append("".join(self.script_buf))
            self.in_script = False
            self.script_type = ""
            self.script_buf = []

    @property
    def title(self):
        return clean(" ".join(self.title_buf))

def _iter_jsonld(value):
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _iter_jsonld(graph)
        for key, item in value.items():
            if key not in ("@graph",):
                if isinstance(item, (dict, list)):
                    yield from _iter_jsonld(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_jsonld(item)

def _types(obj):
    value = obj.get("@type", [])
    return [value.lower()] if isinstance(value, str) else [str(x).lower() for x in value]

def _address(obj):
    addr = obj.get("address", "")
    if isinstance(addr, dict):
        return clean(", ".join(str(addr.get(k, "")) for k in
            ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry") if addr.get(k)))
    if isinstance(addr, str):
        return clean(addr)
    return ""

def _date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            from datetime import timezone
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except (ValueError, TypeError):
        return None

def _extract_structured(parser, page_url):
    events, places = [], []
    for raw in parser.scripts:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _iter_jsonld(data):
            types = _types(obj)
            if "event" in types or any(t.endswith("event") for t in types):
                start = _date(obj.get("startDate"))
                end = _date(obj.get("endDate")) or start
                loc = obj.get("location", {})
                loc_name = loc.get("name", "") if isinstance(loc, dict) else ""
                loc_addr = _address(loc) if isinstance(loc, dict) else ""
                events.append({
                    "id": clean(obj.get("@id") or obj.get("url") or f"{page_url}#{clean(obj.get('name'))}"),
                    "summary": clean(obj.get("name") or "Sauna event"),
                    "start": start,
                    "end": end,
                    "description": clean(obj.get("description", "")),
                    "location": loc_addr or clean(loc_name),
                    "url": urljoin(page_url, str(obj.get("url") or page_url)),
                })
            if any(t in types for t in ("localbusiness", "healthandbeautybusiness", "place", "sportsactivitylocation")):
                name = clean(obj.get("name"))
                if name:
                    places.append({
                        "name": name,
                        "address": _address(obj),
                        "url": urljoin(page_url, str(obj.get("url") or page_url)),
                        "description": clean(obj.get("description", "")),
                    })
    return events, places

async def _get(session, url):
    async with session.get(url, timeout=25, headers=HEADERS) as response:
        response.raise_for_status()
        return await response.text()

def _candidate_links(parser, source_url):
    source_host = urlparse(source_url).netloc.lower().removeprefix("www.")
    candidates = []
    seen = {source_url}
    for link in parser.links:
        url = link["url"].split("#", 1)[0]
        host = urlparse(url).netloc.lower().removeprefix("www.")
        name = clean(link["name"])
        if not url.startswith("https://") or not name or url in seen:
            continue
        if any(word in name.lower() for word in SKIP):
            continue
        # Prefer links on the source domain; external links are only included if the
        # visible label looks like a named venue/event, not generic footer navigation.
        if host != source_host and len(name) < 5:
            continue
        seen.add(url)
        candidates.append({"url": url, "name": name})
    return candidates[:MAX_PAGES_PER_SOURCE]

async def async_collect(session, sources):
    venues_by_key, events_by_key, errors = {}, {}, []
    for source in sources:
        try:
            html = await _get(session, source)
            listing_parser = PageParser(source)
            listing_parser.feed(html)
            candidates = _candidate_links(listing_parser, source)
            # Include source directory itself for resilience.
            candidates.insert(0, {"url": source, "name": listing_parser.title or urlparse(source).netloc})
            for candidate in candidates:
                try:
                    page_html = html if candidate["url"] == source else await _get(session, candidate["url"])
                    parser = PageParser(candidate["url"])
                    parser.feed(page_html)
                    found_events, found_places = _extract_structured(parser, candidate["url"])
                    source_host = urlparse(source).netloc
                    for place in found_places:
                        place["source"] = source_host
                        place["source_directory"] = source
                        key = re.sub(r"[^a-z0-9]+", "", place["name"].lower())
                        if key:
                            if key not in venues_by_key:
                                venues_by_key[key] = place | {"sources": [source], "source_links": [place["url"]]}
                            else:
                                current = venues_by_key[key]
                                if not current.get("address") and place.get("address"):
                                    current["address"] = place["address"]
                                if source not in current["sources"]:
                                    current["sources"].append(source)
                                if place["url"] not in current["source_links"]:
                                    current["source_links"].append(place["url"])
                    for event in found_events:
                        if not event.get("start"):
                            continue
                        key = (event.get("id") or event["summary"], event["start"])
                        event["source_directory"] = source
                        events_by_key[key] = event
                    # If a page is clearly a venue but has no JSON-LD Place, retain its link.
                    label = candidate["name"]
                    key = re.sub(r"[^a-z0-9]+", "", label.lower())
                    if key and candidate["url"] != source and key not in venues_by_key:
                        venues_by_key[key] = {
                            "name": label, "address": "", "url": candidate["url"],
                            "description": "", "source": source_host,
                            "sources": [source], "source_links": [candidate["url"]],
                        }
                except Exception:
                    # A single blocked/removed venue page should not stop the other pages.
                    continue
        except Exception as err:
            errors.append(f"{source}: {err}")
    if not venues_by_key and not events_by_key and errors:
        raise RuntimeError("; ".join(errors))
    return {
        "venues": sorted(venues_by_key.values(), key=lambda x: x["name"].lower()),
        "events": sorted(events_by_key.values(), key=lambda x: x["start"] or ""),
        "source_errors": errors,
        "last_updated": datetime.now().astimezone().isoformat(),
    }
