from datetime import date, datetime
import json

from custom_components.ukga.scraper import (
    PageParser,
    _date,
    _extract_structured,
    _number52_schedule_fallback,
)


def test_date_rejects_invalid_values():
    assert _date(None) is None
    assert _date("not-a-date") is None


def test_date_normalizes_zulu_timestamp():
    assert _date("2026-10-15T18:30:00Z") == "2026-10-15T18:30:00+00:00"


def test_structured_event_is_extracted():
    page_url = "https://example.org/events/"
    document = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "Community Night",
        "startDate": "2026-11-05T18:00:00+00:00",
        "endDate": "2026-11-05T22:00:00+00:00",
        "url": "/events/community-night/",
        "location": {"@type": "Place", "name": "Example Sauna"},
    }
    parser = PageParser(page_url)
    parser.feed(
        '<script type="application/ld+json">'
        + json.dumps(document)
        + "</script>"
    )

    events, _ = _extract_structured(parser, page_url)

    assert len(events) == 1
    assert events[0]["summary"] == "Community Night"
    assert events[0]["start"] == "2026-11-05T18:00:00+00:00"
    assert events[0]["url"] == "https://example.org/events/community-night/"


def test_number52_fallback_only_generates_future_thursday_events():
    today = date.today()
    events = _number52_schedule_fallback(
        "https://www.number52sauna.co.uk/our-events/", "Number 52"
    )

    assert events
    assert all(datetime.fromisoformat(event["start"]).date() >= today for event in events)
    assert all(datetime.fromisoformat(event["start"]).weekday() == 3 for event in events)
    assert all(event["venue"] == "Number 52" for event in events)
    assert all(event["recurring"] is True for event in events)
    assert {event["summary"] for event in events} == {
        "Fetish Night",
        "Sports/Chav Night",
    }
