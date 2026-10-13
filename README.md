# UKGA — UK Gay Saunas & Events for Home Assistant

Custom Home Assistant integration intended for HACS. It starts with these directories and follows venue links, including links to official venue websites:

- [misterb&b — UK Saunas & Cruising](https://www.misterbandb.com/gay-guide/united-kingdom/58-saunas-cruising)
- [Gay Saunas UK](https://gaysaunas.co.uk/uk/)

## Features

- Crawls directory listings, linked venue pages, and likely official venue websites.
- Native Home Assistant calendar entity for dated Schema.org events and published weekday schedules that can be interpreted as recurring events.
- Creates upcoming calendar occurrences for detected weekly and ordinal monthly schedules.
- Venue button attributes include address, Google Maps search URL, official website (when found), description, and source links.
- Deduplicates event occurrences and venue listings where possible.
- Refreshes every six hours.
- Venue-count sensor includes event count, refresh time, configured sources, and source-level errors.

## Event extraction notes

The scraper looks for structured event data and also attempts to interpret visible text schedules on linked pages (for example, a named event listed beside a weekday and hours). For weekly schedules it generates future occurrences for the next 13 weeks; for explicitly ordinal monthly schedules it generates the next several matching dates. If a page only says something vague such as "coming soon", has a JavaScript-only calendar, or blocks automated requests, dates may still be missing. Generated recurring dates are best-effort interpretations of published schedules, not a guarantee that a particular session has not been cancelled. Always check the venue's official website before travelling.

This is a general-purpose HTML scraper, not a bespoke adapter for every sauna website. Page layouts vary, and some external websites may block requests or load events dynamically. It may therefore miss details or occasionally interpret an ambiguous schedule incorrectly. Please review calendar entries and logs before relying on them.

## Install via HACS (custom repository)

1. In Home Assistant, open **HACS → Integrations**.
2. Open the three-dot menu → **Custom repositories**.
3. Add `https://github.com/jonny5509/ukga` and select **Integration**.
4. Download **UK Gay Saunas & Events**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration** and choose **UK Gay Saunas & Events**.
7. Confirm the two source URLs.

## Calendar dashboard

Add the created calendar entity to a Calendar dashboard card. The entity ID is typically `calendar.ukga_events`, but Home Assistant may adjust it to avoid a name conflict.

## Venue website and address buttons

Venue button entities expose `official_website`, `google_maps_url`, `address`, `description`, `source_url`, and `source_links` attributes. A Home Assistant button entity cannot open a URL by itself. To make a dashboard button open the official website, install the community `button-card` frontend and use this example, replacing the entity ID with one created by your instance:

```yaml
type: custom:button-card
entity: button.replace_with_venue_get_address
name: Official website
icon: mdi:web
tap_action:
  action: url
  url: >
    [[[ return entity.attributes.official_website || entity.attributes.source_url; ]]]
```

To open Google Maps instead, use this tap action:

```yaml
tap_action:
  action: url
  url: >
    [[[ return entity.attributes.google_maps_url; ]]]
```

## Development status

This is a best-effort integration and has not been executed in a Home Assistant runtime or tested against every live source page in this change. Check Home Assistant logs and verify extracted events against venue websites. Respect source website terms and rate limits.
