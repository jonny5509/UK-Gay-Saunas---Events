"""Scrape venue listings and event schedules from the configured directory only."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin, urlparse


HEADERS = {"User-Agent": "Home Assistant UKGA integration/0.2 (personal use)"}
SKIP = ("privacy", "cookies", "contact", "about us", "terms", "login", "register",
        "facebook", "instagram", "tiktok", "youtube", "twitter", "whatsapp")
DAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_NUM = {name: i for i, name in enumerate(DAY_NAMES)}
TIME_RE = re.compile(r"(?P<start>(?:[01]?\d|2[0-3])[:.][0-5]\d)\s*(?:-|–|—|to)\s*(?P<end>(?:[01]?\d|2[0-3])[:.][0-5]\d)", re.I)
ORDINAL_RE = re.compile(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|last)\b", re.I)
EVENT_WORDS = ("event", "night", "party", "session", "day", "special", "foam", "bear",
               "naked", "fetish", "discount", "social", "themed", "workout", "club")

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
        self._h1 = False
        self.h1_buf = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self._title = True
        if tag == "h1":
            self._h1 = True
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
        if self._h1:
            self.h1_buf.append(value)
        if self.anchor is not None and value:
            self.anchor["text"].append(value)
        if self.in_script:
            self.script_buf.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self._title = False
        if tag == "h1":
            self._h1 = False
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

    @property
    def h1(self):
        return clean(" ".join(self.h1_buf))


def _is_region_or_directory_label(value):
    value = clean(value).lower()
    if not value or re.search(r"\b\d+\s+venues?\b", value):
        return True
    if re.match(r"^(?:north east|north west|south east|south west|east midlands|west midlands|east of england|west yorkshire|south yorkshire|east yorkshire|scotland|wales|northern ireland|england|london|newcastle|sunderland)\b", value):
        return True
    return any(term in value for term in ("sauna directory", "gay saunas uk", "saunas & cruising"))


def _venue_name_from_page(parser, fallback):
    # Prefer the venue page's own heading/title over the directory card label.
    for raw in (parser.h1, parser.title):
        candidate = clean(raw)
        if not candidate:
            continue
        candidate = re.split(r"\s+[|–—-]\s+", candidate, maxsplit=1)[0].strip()
        if not _is_region_or_directory_label(candidate) and len(candidate) >= 3:
            return candidate
    return fallback

def _iter_jsonld(value):
    if isinstance(value, dict):
        yield value
        for key, item in value.items():
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
    return clean(addr) if isinstance(addr, str) else ""

def _date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
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
            if any(t == "event" or t.endswith("event") for t in types):
                start = _date(obj.get("startDate"))
                end = _date(obj.get("endDate")) or start
                loc = obj.get("location", {})
                loc_name = loc.get("name", "") if isinstance(loc, dict) else ""
                loc_addr = _address(loc) if isinstance(loc, dict) else ""
                events.append({
                    "id": clean(obj.get("@id") or obj.get("url") or f"{page_url}#{clean(obj.get('name'))}"),
                    "summary": clean(obj.get("name") or "Sauna event"), "start": start, "end": end,
                    "description": clean(obj.get("description", "")),
                    "location": loc_addr or clean(loc_name),
                    "url": urljoin(page_url, str(obj.get("url") or page_url)),
                })
            if any(t in types for t in ("localbusiness", "healthandbeautybusiness", "place", "sportsactivitylocation")):
                name = clean(obj.get("name"))
                if name:
                    places.append({"name": name, "address": _address(obj),
                        "url": urljoin(page_url, str(obj.get("url") or page_url)),
                        "description": clean(obj.get("description", ""))})
    return events, places

def _parse_clock(value):
    if not value:
        return None
    value = value.replace(".", ":")
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None

def _recurring_events(parser, page_url, venue_name):
    """Infer future calendar occurrences only from explicit published weekday schedules."""
    found = {}
    chunks = parser.text
    today = date.today()
    for i, chunk in enumerate(chunks):
        low = chunk.lower()
        day = next((d for d in DAY_NAMES if re.search(rf"\b{d}\b", low)), None)
        if not day:
            continue
        title = ""
        for previous in reversed(chunks[max(0, i - 3):i]):
            candidate = clean(previous)
            candidate_low = candidate.lower()
            if (len(candidate) >= 3 and len(candidate) <= 90
                    and not any(x in candidate_low for x in ("what's on", "events & themed", "opening hours", "when to visit"))
                    and not any(re.search(rf"\b{x}\b", candidate_low) for x in DAY_NAMES)
                    and not re.fullmatch(r"[\d:–—\- ]+", candidate)):
                title = candidate
                break
        if not title:
            title = re.split(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", chunk, flags=re.I)[0].strip(" ·-–:")
        if not title or len(title) < 3:
            continue
        if not any(word in title.lower() for word in EVENT_WORDS):
            continue
        context = " ".join(chunks[i:min(len(chunks), i + 4)])
        times = TIME_RE.search(context)
        start_clock = _parse_clock(times.group("start")) if times else time(12, 0)
        end_clock = _parse_clock(times.group("end")) if times else start_clock
        if not start_clock:
            start_clock = time(12, 0)
        if not end_clock:
            end_clock = start_clock
        ordinal_text = " ".join(chunks[max(0, i - 3):min(len(chunks), i + 4)])
        ordinal_match = ORDINAL_RE.search(ordinal_text)
        ordinal = ordinal_match.group(1).lower() if ordinal_match else None
        monthly = bool(ordinal)
        dates = []
        if monthly:
            for month_offset in range(0, 7):
                month_index = today.month - 1 + month_offset
                year = today.year + month_index // 12
                month = month_index % 12 + 1
                first = date(year, month, 1)
                delta = (DAY_NUM[day] - first.weekday()) % 7
                first_occurrence = first + timedelta(days=delta)
                if ordinal in ("first", "1st"):
                    occurrence = first_occurrence
                elif ordinal in ("second", "2nd"):
                    occurrence = first_occurrence + timedelta(days=7)
                elif ordinal in ("third", "3rd"):
                    occurrence = first_occurrence + timedelta(days=14)
                elif ordinal in ("fourth", "4th"):
                    occurrence = first_occurrence + timedelta(days=21)
                else:
                    next_month = date(year + (month == 12), month % 12 + 1, 1)
                    occurrence = next_month - timedelta(days=1)
                    occurrence -= timedelta(days=(occurrence.weekday() - DAY_NUM[day]) % 7)
                if occurrence >= today:
                    dates.append(occurrence)
        else:
            delta = (DAY_NUM[day] - today.weekday()) % 7
            first_day = today + timedelta(days=delta)
            dates = [first_day + timedelta(days=7 * n) for n in range(13)]
        for occurrence in dates:
            start_dt = datetime.combine(occurrence, start_clock).astimezone()
            end_date = occurrence + timedelta(days=1) if end_clock < start_clock else occurrence
            end_dt = datetime.combine(end_date, end_clock).astimezone()
            event = {
                "id": f"{page_url}#{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}-{occurrence.isoformat()}",
                "summary": clean(title), "start": start_dt.isoformat(), "end": end_dt.isoformat(),
                "description": f"Published recurring schedule. Please confirm details with the venue. Venue: {venue_name}",
                "location": venue_name, "url": page_url, "recurring": True,
            }
            found[(event["summary"].lower(), event["start"])] = event
    return list(found.values())

async def _get(session, url):
    async with session.get(url, timeout=25, headers=HEADERS) as response:
        response.raise_for_status()
        return await response.text()

def _candidate_links(parser, source_url):
    source_host = urlparse(source_url).netloc.lower().removeprefix("www.")
    candidates, seen = [], {source_url}
    for link in parser.links:
        url = link["url"].split("#", 1)[0]
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        # Keep all crawling on the configured directory host; do not scrape venue websites.
        if host != source_host:
            continue
        name = clean(link["name"])
        # Keep region links so we can follow them to individual venue pages.
        if parsed.scheme not in ("http", "https") or not host or not name or url in seen:
            continue
        if any(word in name.lower() for word in SKIP):
            continue
        label = name.lower()
        priority = 0 if any(x in label for x in ("official website", "visit website", "website", "web site")) else (
            1 if host != source_host else 2)
        if host == source_host and len(name) < 3:
            continue
        seen.add(url)
        candidates.append({"url": url, "name": name, "priority": priority, "host": host})
    return sorted(candidates, key=lambda x: x["priority"])

async def async_collect(session, sources):
    venues_by_key, events_by_key, errors = {}, {}, []
    source_stats = []
    for source in sources:
        source_venue_keys = set()
        pages_done = 0
        try:
            html = await _get(session, source)
            listing_parser = PageParser(source)
            listing_parser.feed(html)
            source_path = urlparse(source).path.rstrip("/")
            initial = _candidate_links(listing_parser, source)
            queue = []
            queued_pages = set()
            seen_pages = set()

            def enqueue(url, name, official=False):
                url = url.split("#", 1)[0]
                path = urlparse(url).path.rstrip("/")
                # Only crawl the selected region and its venue subpages, not the
                # site's unrelated city guides, other regions, or general pages.
                if urlparse(url).netloc.lower().removeprefix("www.") != urlparse(source).netloc.lower().removeprefix("www."):
                    return
                if path != source_path and not path.startswith(source_path + "/"):
                    return
                if url in queued_pages or url in seen_pages:
                    return
                queued_pages.add(url)
                queue.append({"url": url, "name": name, "directory": source, "official": official})

            enqueue(source, listing_parser.title or urlparse(source).netloc)
            for item in initial:
                item_path = urlparse(item["url"]).path.rstrip("/")
                # Venue cards are direct children of the selected regional directory.
                # Ignore deeper pages such as event articles, tags, and general content.
                if (item_path != source_path
                        and urlparse(item["url"]).path.rstrip("/").rsplit("/", 1)[0] == source_path
                        and not _is_region_or_directory_label(item["name"])):
                    enqueue(item["url"], item["name"], False)

            while queue:
                candidate = queue.pop(0)
                url = candidate["url"].split("#", 1)[0]
                if url in seen_pages:
                    continue
                seen_pages.add(url)
                try:
                    page_html = html if url == source else await _get(session, url)
                    parser = PageParser(url)
                    parser.feed(page_html)
                    pages_done += 1
                    found_events, found_places = _extract_structured(parser, url)
                    source_host = urlparse(source).netloc
                    venue_label = candidate["name"] if url == source else _venue_name_from_page(parser, candidate["name"])
                    # Venue records are intentionally limited to name and source page URL.
                    event_venue = next((p["name"] for p in found_places if p.get("name")), venue_label)
                    for event in found_events:
                        if not event.get("start"):
                            continue
                        event["source_directory"] = source
                        events_by_key[(event.get("id") or event["summary"], event["start"])] = event
                    for event in _recurring_events(parser, url, event_venue):
                        event["source_directory"] = source
                        events_by_key[(event["id"], event["start"])] = event
                    # Save the resolved page heading/title, not the directory card text.
                    # The card text may be a regional label such as "London · 6 venues".
                    label = venue_label
                    key = re.sub(r"[^a-z0-9]+", "", label.lower())
                    if key and url != source and not _is_region_or_directory_label(label):
                        if key not in venues_by_key:
                            venues_by_key[key] = {"name": label, "url": url}
                        source_venue_keys.add(key)
                    # Do not recursively enqueue links found on venue pages. That caused
                    # event articles, tag pages, and other nested pages to be mistaken for
                    # additional venues. Venue discovery is limited to links on each
                    # configured regional directory page (the initial queue above).
                except Exception as err:
                    if url == source:
                        errors.append(f"{source}: {err}")
                    continue
        except Exception as err:
            errors.append(f"{source}: {err}")
        source_stats.append({
            "source": source,
            "pages_visited": pages_done,
            "venues_found": len(source_venue_keys),
            "events_found": sum(1 for event in events_by_key.values() if event.get("source_directory") == source),
        })

    if not venues_by_key and not events_by_key and errors:
        raise RuntimeError("; ".join(errors))
    return {
        "venues": sorted(venues_by_key.values(), key=lambda x: x["name"].lower()),
        "events": sorted(
            ({
                "summary": event.get("summary"),
                "start": event.get("start"),
                "end": event.get("end"),
                "location": event.get("location"),
                "url": event.get("url"),
                "source_directory": event.get("source_directory"),
                "recurring": event.get("recurring", False),
            } for event in events_by_key.values()),
            key=lambda x: x["start"] or "",
        ),
        "source_errors": errors,
        "source_stats": source_stats,
        "sources": sources,
        "last_updated": datetime.now().astimezone().isoformat(),
    }
