"""Scrape venue directories, then enrich matched venues from their official websites."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import asyncio
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

try:
    with open(__file__.replace("scraper.py", "official_websites.json"), encoding="utf-8") as _website_file:
        OFFICIAL_WEBSITES = json.load(_website_file)
except (OSError, json.JSONDecodeError):
    OFFICIAL_WEBSITES = {}

WEBSITE_ALIASES = {
    "basement": "basementcomplexmanchester",
    "sweatbox": "sweatboxsoho",
    "saunasauna": "saunasaunanorthwich",
    "touchsauna": "touchsaunaswindon",
    "splash": "splashspaleicester",
    "w3complex": "w3saunablackpool",
    "heroeshealthclub": "heroessaunastourbridge",
    "manticorespaplymouth": "manticore",
    "manticorespa": "manticore",
    "pleasuredromegaysaunalondon": "pleasuredrome",
    "pleasuredromelondon": "pleasuredrome",
    "steamerquaysaunatorquay": "steamerquay",
    "theboilerroomsaunabrighton": "theboilerroomhove",
    "theboilerroomsaunahove": "theboilerroomhove",
    "theboilerroomsauna": "theboilerroomhove",
    "lockerroomlondon": "lockerroomsaunalondon",
    "clubzeusmansfield": "clubzeussaunamansfield",
    "dolphingaysaunanewbrightonmerseyside": "dolphinsaunanewbrighton",
    "dolphin": "dolphinsaunanewbrighton",
    "e15club": "e15clublondon",
    "gentryspa": "gentryspahull",
    "heroessauna": "heroessaunastourbridge",
    "me1saunaandsteam": "me1saunarochester",
    "number52sauna": "number52saunanewcastle",
    "plasticivysauna": "plasticivysaunadewsbury",
    "thepipeworksleeds": "pipeworksleeds",
    "pipeworks": "pipeworksleeds",
    "yumbo": "yumbobirmingham",
    "greenhousesaunaluton": "greenhousesaunaluton",
    "greenhousesaunadarlaston": "greenhousesaunadarlaston",
}
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
            label = clean(" ".join(str(attrs.get(k, "")) for k in ("aria-label", "title", "alt")))
            self.anchor = {"url": urljoin(self.base, attrs["href"]), "text": [label] if label else []}
        elif tag == "img" and self.anchor is not None:
            image_label = clean(" ".join(str(attrs.get(k, "")) for k in ("alt", "title", "aria-label")))
            if image_label:
                self.anchor["text"].append(image_label)
        # Some directory templates use buttons or image hotspots instead of anchors.
        if tag in ("button", "area") or (tag == "div" and any(k in attrs for k in ("data-href", "data-url", "data-website"))):
            raw_url = next((attrs.get(k) for k in ("href", "data-href", "data-url", "data-website") if attrs.get(k)), "")
            if not raw_url and attrs.get("onclick"):
                match = re.search(r"""(?:location(?:\.href)?|window\.open)\s*\(?\s*['"](https?://[^'"]+)['"]""", attrs["onclick"])
                raw_url = match.group(1) if match else ""
            if raw_url:
                label = clean(" ".join(str(attrs.get(k, "")) for k in ("aria-label", "title", "alt", "class")))
                self.links.append({"url": urljoin(self.base, raw_url), "name": label})
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
            # Retain unlabeled links too: linked logos/icons often have no text,
            # and the destination hostname can still identify the venue website.
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


def _official_website(name):
    """Return a manually researched official website for a known venue name."""
    key = re.sub(r"[^a-z0-9]+", "", clean(name).lower())
    lookup_key = WEBSITE_ALIASES.get(key, key)
    record = OFFICIAL_WEBSITES.get(lookup_key)
    if not record:
        # Directory titles often add a town or generic suffix to the known venue name.
        # Use the longest unambiguous normalized match rather than requiring exact spelling.
        matches = [
            known_key for known_key in OFFICIAL_WEBSITES
            if len(known_key) >= 8 and (key.startswith(known_key) or known_key.startswith(key))
        ]
        if matches:
            longest = max(matches, key=len)
            if sum(1 for item in matches if len(item) == len(longest)) == 1:
                record = OFFICIAL_WEBSITES[longest]
    if not record:
        return None
    return {"official_website": record["url"], "website_match_status": record.get("status", "verified").title()}

def _discover_official_website(parser, venue_name):
    """Find an official-site link explicitly exposed on a venue's own directory page."""
    venue_key = re.sub(r"[^a-z0-9]+", "", clean(venue_name).lower())
    ignored_hosts = (
        "gaysaunas.co.uk", "facebook.com", "instagram.com", "tiktok.com",
        "youtube.com", "twitter.com", "x.com", "wa.me", "whatsapp.com",
        "google.com", "maps.google", "tripadvisor.", "travelgay.com",
        "thegayuk.com", "patroc.com", "wikipedia.org", "linktr.ee",
        "booking.com", "eventbrite.", "meetup.com",
    )
    candidates = []
    for link in parser.links:
        url = link.get("url", "").split("#", 1)[0]
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        label = clean(link.get("name", "")).lower()
        if parsed.scheme not in ("http", "https") or not host:
            continue
        if any(bad in host for bad in ignored_hosts):
            continue
        if any(word in label for word in ("facebook", "instagram", "tiktok", "youtube", "privacy", "cookie")):
            continue
        # Only trust an explicitly labelled website link or a domain that resembles
        # the venue name. This avoids treating adverts and unrelated outbound links as official.
        label_match = any(term in label for term in ("official website", "visit website", "venue website", "website", "web site", "visit site", "homepage", "official site"))
        host_key = re.sub(r"[^a-z0-9]+", "", host.split(".")[0])
        name_tokens = [token for token in re.sub(r"[^a-z0-9]+", " ", clean(venue_name).lower()).split()
                       if len(token) >= 3 and token not in ("the", "and", "sauna", "health", "club", "spa", "complex", "london")]
        # Ignore generic labels and don't match tiny/common fragments against a domain.
        host_match = any(token in host_key for token in name_tokens)
        if not label_match and not host_match:
            continue
        score = (5 if label_match else 0) + (4 if host_match else 0)
        if parsed.path in ("", "/"):
            score += 1
        candidates.append((score, url))

    # Some venue pages publish the official domain in Schema.org sameAs fields
    # rather than a visible website link. Only use external sameAs URLs here.
    for raw in parser.scripts:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _iter_jsonld(data):
            values = obj.get("sameAs", [])
            if isinstance(values, str):
                values = [values]
            for value in values or []:
                if not isinstance(value, str):
                    continue
                parsed = urlparse(value)
                host = parsed.netloc.lower().removeprefix("www.")
                if parsed.scheme not in ("http", "https") or not host or any(bad in host for bad in ignored_hosts):
                    continue
                host_key = re.sub(r"[^a-z0-9]+", "", host.split(".")[0])
                if any(token in host_key for token in name_tokens):
                    candidates.append((6, value))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return {"official_website": candidates[0][1], "website_match_status": "Discovered"}


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



def _extract_private_rooms(parser):
    """Return Yes/No only for explicit private-room claims; otherwise unknown."""
    text = clean(" ".join(parser.text))
    claims = []
    for match in re.finditer(r"\bprivate\s+(?:rooms?|cabins?)\b", text, re.I):
        context = text[max(0, match.start() - 100):min(len(text), match.end() + 100)].lower()
        negative = re.search(
            r"\b(?:no|not|never|without|unavailable|unavailable|doesn['’]?t\s+(?:have|offer|provide)|do\s+not\s+(?:have|offer|provide)|aren['’]?t\s+available)\b",
            context,
        )
        positive = re.search(
            r"\b(?:available|offer(?:s|ed)?|provid(?:e|es|ed)|have|has|book(?:able)?|rent(?:able)?|hire|yes)\b",
            context,
        )
        if negative:
            claims.append("No")
        elif positive:
            claims.append("Yes")
    if not claims or len(set(claims)) > 1:
        return None
    return claims[0]

def _extract_pricing(parser):
    """Extract published venue prices from labelled text and structured offers."""
    text = clean(" ".join(parser.text))
    # Prefer an explicitly labelled entry/admission/pricing section. Keep a short
    # context so we don't mistake phone numbers, postcodes, or dates for prices.
    labels = (
        r"(?:entry|entrance|admission|door|day\s*pass|session|membership|"
        r"prices?|pricing|costs?|fees?|tariff|offers?)"
    )
    currency_price = r"(?:£\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\bGBP\s?\d{1,4}(?:\.\d{1,2})?)"
    labelled_patterns = (
        rf"{labels}\b[^.;]{{0,65}}?({currency_price}(?:\s*(?:-|–|—|to)\s*(?:£\s?)?\d{{1,4}}(?:\.\d{{1,2}})?)?(?:\s*(?:per\s+(?:person|visit|session|day)|each))?)",
        rf"({currency_price}(?:\s*(?:-|–|—|to)\s*(?:£\s?)?\d{{1,4}}(?:\.\d{{1,2}})?)?)\s*[^.;]{{0,45}}\b(?:entry|entrance|admission|day\s*pass|session|per\s+person)\b",
        r"\b(free\s+(?:entry|admission)|(?:entry|admission)\s+(?:is\s+)?free|no\s+entry\s+fee)\b",
    )
    for pattern in labelled_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = clean(match.group(1)).strip(" :-–")
            if value:
                return value[:140]

    # Some sites publish a compact price list without a heading immediately before
    # every amount. Only accept a short run of prices when the page mentions pricing.
    if re.search(r"\b(?:pricing|prices?|entry|admission|day\s*pass|tariff|fees?)\b", text, re.I):
        excerpt_match = re.search(
            r"\b(?:pricing|prices?|entry\s+(?:price|fee)|admission|day\s*pass|tariff|fees?)\b"
            r"[^.;]{0,35}((?:£\s?\d{1,4}(?:\.\d{1,2})?(?:\s*(?:-|–|to)\s*£?\s?\d{1,4}(?:\.\d{1,2})?)?"
            r"(?:\s*(?:,|/|or|and)\s*£?\s?\d{1,4}(?:\.\d{1,2})?)?)(?:[^.;]{0,25}))",
            text, re.I,
        )
        if excerpt_match:
            value = clean(excerpt_match.group(1)).strip(" :-–")
            if value:
                return value[:140]

    # Schema.org offers are often present even when the visible price list is not.
    for raw in parser.scripts:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _iter_jsonld(data):
            offers = obj.get("offers")
            if isinstance(offers, dict):
                offers = [offers]
            values = []
            for offer in offers or []:
                if not isinstance(offer, dict) or offer.get("price") is None:
                    continue
                currency = clean(offer.get("priceCurrency") or "GBP")
                values.append(f"{currency} {offer['price']}")
            if values:
                return ", ".join(dict.fromkeys(values))[:140]
            # Product-like price ranges are occasionally published at the venue level.
            low, high = obj.get("lowPrice"), obj.get("highPrice")
            if low is not None and high is not None:
                currency = clean(obj.get("priceCurrency") or "GBP")
                return f"{currency} {low}–{high}"[:140]
    return None

def _event_price(obj):
    offers = obj.get("offers")
    if isinstance(offers, dict):
        offers = [offers]
    values = []
    for offer in offers or []:
        if isinstance(offer, dict) and offer.get("price") is not None:
            currency = clean(offer.get("priceCurrency") or "GBP")
            values.append(f"{currency} {offer['price']}")
    return ", ".join(dict.fromkeys(values)) or None

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
                    "price": _event_price(obj),
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


def _extract_opening_hours(parser):
    """Extract a weekly schedule only when explicit published hours can be parsed."""
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    aliases = {
        "mo": 0, "mon": 0, "monday": 0,
        "tu": 1, "tue": 1, "tues": 1, "tuesday": 1,
        "we": 2, "wed": 2, "wednesday": 2,
        "th": 3, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3,
        "fr": 4, "fri": 4, "friday": 4,
        "sa": 5, "sat": 5, "saturday": 5,
        "su": 6, "sun": 6, "sunday": 6,
    }
    hours = {day: [] for day in weekdays}

    def clock(value):
        match = re.fullmatch(r"(\d{1,2})[:.](\d{2})", str(value).strip())
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if minute > 59 or hour > 24 or (hour == 24 and minute != 0):
            return None
        return f"{hour:02d}:{minute:02d}"

    def day_indices(value):
        value = re.sub(r"^.*?/", "", str(value).lower()).replace("http:", "").replace("https:", "")
        value = value.strip().rstrip("/")
        if value in aliases:
            return [aliases[value]]
        if "-" in value:
            left, right = [part.strip() for part in value.split("-", 1)]
            if left in aliases and right in aliases:
                a, b = aliases[left], aliases[right]
                return list(range(a, b + 1)) if a <= b else list(range(a, 7)) + list(range(0, b + 1))
        return []

    def add_range(day_values, opening, closing):
        opening, closing = clock(opening), clock(closing)
        if not opening or not closing or opening == closing:
            return False
        indices = []
        if isinstance(day_values, str):
            day_values = [day_values]
        for day_value in (day_values or []):
            raw = str(day_value).lower().replace("https://schema.org/", "").replace("http://schema.org/", "")
            for part in re.split(r"\s*,\s*", raw):
                indices.extend(day_indices(part))
        if not indices:
            return False
        for index in set(indices):
            hours[weekdays[index]].append([opening, closing])
        return True

    found = False
    for raw in parser.scripts:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _iter_jsonld(data):
            specs = obj.get("openingHoursSpecification")
            if isinstance(specs, dict):
                specs = [specs]
            for spec in specs or []:
                if isinstance(spec, dict):
                    found = add_range(spec.get("dayOfWeek", []), spec.get("opens", ""), spec.get("closes", "")) or found
            published = obj.get("openingHours", [])
            if isinstance(published, str):
                published = [published]
            for entry in published or []:
                match = re.search(
                    r"([A-Za-z]{2,9}(?:\s*-\s*[A-Za-z]{2,9})?(?:\s*,\s*[A-Za-z]{2,9})*)\s+(\d{1,2}[:.]\d{2})\s*-\s*(\d{1,2}[:.]\d{2})",
                    str(entry),
                )
                if match:
                    found = add_range(re.split(r"\s*,\s*", match.group(1)), match.group(2), match.group(3)) or found

    # As a fallback, parse time ranges only in an explicitly labelled opening-hours section.
    if not found:
        text = " ".join(parser.text)
        section = re.search(r"opening\s+hours?\b", text, re.I)
        if section:
            excerpt = text[section.end():section.end() + 900]
            pattern = re.compile(
                r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)\b"
                r"[^A-Za-z0-9]{0,12}(\d{1,2}[:.]\d{2})\s*(?:-|–|—|to)\s*(\d{1,2}[:.]\d{2})",
                re.I,
            )
            for match in pattern.finditer(excerpt):
                found = add_range([match.group(1)], match.group(2), match.group(3)) or found

    if not found:
        return None
    return hours

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


def _official_related_pages(parser, base_url):
    """Select a small set of relevant same-site pages for venue details and events."""
    base = urlparse(base_url)
    base_host = base.netloc.lower().removeprefix("www.")
    relevant = ("opening", "hour", "price", "pricing", "admission", "entry", "fee", "fees",
                "tariff", "rate", "cost", "day-pass", "daypass", "membership", "facility",
                "facilities", "private", "room", "event", "whatson", "what-s-on", "calendar",
                "visit", "sauna")
    selected, seen = [], {base_url.rstrip("/")}
    for link in parser.links:
        url = link.get("url", "").split("#", 1)[0].rstrip("/")
        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme not in ("http", "https") or host != base_host or url in seen:
            continue
        label_path = (link.get("name", "") + " " + parsed.path).lower()
        if not any(word in label_path for word in relevant):
            continue
        if any(word in label_path for word in ("privacy", "cookie", "login", "register", "shop", "booking")):
            continue
        seen.add(url)
        selected.append(url)
        if len(selected) >= 10:
            break
    return selected


async def _enrich_from_official_website(session, venue):
    """Fetch a curated official website and extract only explicit venue information."""
    url = venue.get("official_website")
    if not url:
        return [], None
    try:
        html = await _get(session, url)
    except Exception as err:
        return [], f"{venue.get('name')}: official website fetch failed: {err}"
    homepage = PageParser(url)
    homepage.feed(html)
    pages = [(url, homepage)]
    # Many sites publish hours, prices, and events on dedicated pages rather than home.
    for page_url in _official_related_pages(homepage, url):
        try:
            page_html = await _get(session, page_url)
            parser = PageParser(page_url)
            parser.feed(page_html)
            pages.append((page_url, parser))
        except Exception:
            continue

    extracted = set()
    events = []
    venue_name = venue.get("name") or homepage.h1 or "Sauna"
    for page_url, parser in pages:
        hours = _extract_opening_hours(parser)
        if hours and "opening_hours" not in extracted:
            venue["opening_hours"] = hours
            venue["opening_hours_source"] = "official_website"
            venue["opening_hours_source_url"] = page_url
            extracted.add("opening_hours")
        pricing = _extract_pricing(parser)
        if pricing and "pricing" not in extracted:
            venue["pricing"] = pricing
            venue["pricing_source"] = "official_website"
            venue["pricing_source_url"] = page_url
            extracted.add("pricing")
        private_rooms = _extract_private_rooms(parser)
        if private_rooms and "private_rooms" not in extracted:
            venue["private_rooms"] = private_rooms
            venue["private_rooms_source"] = "official_website"
            venue["private_rooms_source_url"] = page_url
            extracted.add("private_rooms")

        structured_events, places = _extract_structured(parser, page_url)
        for place in places:
            if place.get("name") and re.sub(r"[^a-z0-9]", "", place.get("name").lower()) == re.sub(r"[^a-z0-9]", "", venue_name.lower()):
                venue["official_name"] = place["name"]
                break
        for event in structured_events:
            if not event.get("start"):
                continue
            event["venue"] = venue_name
            event["source_directory"] = "official_website"
            event["source_type"] = "official_website"
            event["url"] = event.get("url") or page_url
            events.append(event)
        for event in _recurring_events(parser, page_url, venue_name):
            event["venue"] = venue_name
            event["source_directory"] = "official_website"
            event["source_type"] = "official_website"
            events.append(event)
    return events, None


async def _enrich_venues_from_official_websites(session, venues):
    """Enrich in parallel with a small concurrency limit; directory data remains fallback."""
    semaphore = asyncio.Semaphore(5)

    async def enrich(venue):
        async with semaphore:
            return venue, await _enrich_from_official_website(session, venue)

    results = await asyncio.gather(*[
        enrich(venue) for venue in venues if venue.get("official_website")
    ], return_exceptions=True)
    events, errors = [], []
    for result in results:
        if isinstance(result, Exception):
            errors.append(f"Official website enrichment failed: {result}")
            continue
        venue, outcome = result
        venue_events, error = outcome
        events.extend(venue_events)
        if error:
            errors.append(error)
    return events, errors


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
                        event["venue"] = venue_label
                        event["source_directory"] = source
                        events_by_key[(event.get("id") or event["summary"], event["start"])] = event
                    for event in _recurring_events(parser, url, event_venue):
                        event["venue"] = venue_label
                        event["source_directory"] = source
                        events_by_key[(event["id"], event["start"])] = event
                    # Save the resolved page heading/title, not the directory card text.
                    # The card text may be a regional label such as "London · 6 venues".
                    label = venue_label
                    key = re.sub(r"[^a-z0-9]+", "", label.lower())
                    if key and url != source and not _is_region_or_directory_label(label):
                        if key not in venues_by_key:
                            venues_by_key[key] = {"name": label, "url": url}
                        # Prefer the curated mapping; if absent, use a clearly labelled
                        # outbound website link published on the venue's own directory page.
                        website = _official_website(label) or _discover_official_website(parser, label)
                        if website:
                            venues_by_key[key].update(website)
                        opening_hours = _extract_opening_hours(parser)
                        if opening_hours:
                            venues_by_key[key]["opening_hours"] = opening_hours
                        pricing = _extract_pricing(parser)
                        if pricing:
                            venues_by_key[key]["pricing"] = pricing
                            venues_by_key[key]["pricing_source"] = "directory"
                            venues_by_key[key]["pricing_source_url"] = url
                        private_rooms = _extract_private_rooms(parser)
                        if private_rooms:
                            venues_by_key[key]["private_rooms"] = private_rooms
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

    # Official websites are the preferred source for explicit venue details.
    # Keep directory-derived values as fallbacks when an official site publishes no value.
    official_events, official_errors = await _enrich_venues_from_official_websites(
        session, list(venues_by_key.values())
    )
    errors.extend(official_errors)
    official_event_keys = set()
    for event in official_events:
        event_key = (
            re.sub(r"[^a-z0-9]+", "", clean(event.get("summary")).lower()),
            event.get("start"),
            re.sub(r"[^a-z0-9]+", "", clean(event.get("venue")).lower()),
        )
        official_event_keys.add(event_key)
        events_by_key[event_key] = event
    # When both sources describe the same event at the same time, retain the official-site version.
    for existing_key, event in list(events_by_key.items()):
        if event.get("source_type") == "official_website":
            continue
        comparable = (
            re.sub(r"[^a-z0-9]+", "", clean(event.get("summary")).lower()),
            event.get("start"),
            re.sub(r"[^a-z0-9]+", "", clean(event.get("venue")).lower()),
        )
        if comparable in official_event_keys:
            events_by_key.pop(existing_key, None)

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
                "venue": event.get("venue"),
                "description": event.get("description"),
                "price": event.get("price"),
                "url": event.get("url"),
                "source_directory": event.get("source_directory"),
                "recurring": event.get("recurring", False),
                "source_type": event.get("source_type", "directory"),
            } for event in events_by_key.values()),
            key=lambda x: x["start"] or "",
        ),
        "source_errors": errors,
        "source_stats": source_stats,
        "sources": sources,
        "last_updated": datetime.now().astimezone().isoformat(),
    }
