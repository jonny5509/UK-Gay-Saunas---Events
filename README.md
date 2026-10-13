# UKGA — UK Gay Saunas & Events for Home Assistant

Custom Home Assistant integration intended for HACS. It reads two configurable directories:

- [misterb&b — UK Saunas & Cruising](https://www.misterbandb.com/gay-guide/united-kingdom/58-saunas-cruising)
- [Gay Saunas UK](https://gaysaunas.co.uk/uk/)

## Features

- Native Home Assistant calendar entity for events with explicit dates found in Schema.org JSON-LD on directory or linked pages.
- One venue/listing button per extracted entry, exposing a Google Maps search URL and the source listing link.
- Deduplicates listings by normalized name and combines source links where names match.
- Refreshes every six hours.
- Venue-count sensor with event count, refresh time, and source errors.

## Important limitations

These websites are directories, not guaranteed structured event feeds. Events are added to the calendar only when a page exposes a parseable date in structured Schema.org event data. If an event is described only in prose (for example, "every Friday") this version does not guess future dates. The HTML parser is best-effort and may need updating if either site changes its markup. Addresses are filled when structured address data is present; otherwise the Maps button searches for the venue name.

Please verify event schedules and venue details with the source before travelling. This community integration is not affiliated with either directory and should respect their terms and rate limits.

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

## Get-address dashboard button

A Home Assistant button entity cannot open a URL by itself. To make a dashboard button open Google Maps, install the community `button-card` frontend and use this example, replacing the entity ID with one created by your instance:

```yaml
type: custom:button-card
entity: button.replace_with_venue_get_address
name: Get address
icon: mdi:map-marker
tap_action:
  action: url
  url: >
    [[[ return entity.attributes.google_maps_url; ]]]
```

Each button also exposes `address`, `source_url`, `source_directory`, and `source_links` attributes.

## Development status

Initial implementation. It has not been validated against every live page or Home Assistant release. Test in your installation and check logs before relying on it.
