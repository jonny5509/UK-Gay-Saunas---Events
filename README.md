# UKGA — UK Gay Saunas & Events for Home Assistant

A best-effort Home Assistant custom integration for discovering UK sauna venues and their published events. It is designed for HACS and scrapes configured directory pages plus linked official venue websites.

## Features

- Crawls the configured directory URLs and follows venue pages within each directory.
- Enriches venue information from curated or clearly linked official websites.
- Provides a Home Assistant calendar, next-event sensors, opening-status, pricing, private-room and official-website sensors, information buttons, favourites and notification-subscription switches.
- Detects Schema.org events and attempts to interpret explicitly published weekly or ordinal monthly schedules.
- Adds entities for venues discovered on later refreshes and uses stable URL-derived venue identities.
- Stores favourite and notification preferences across restarts.
- Refreshes every 30 minutes.
- Exposes crawl counts, last refresh time, source-level errors and event counts on the directory sensor.

## Installation

1. In Home Assistant, open **HACS → Integrations**.
2. Open the three-dot menu → **Custom repositories**.
3. Add `https://github.com/jonny5509/UK-Gay-Saunas-Events` and select **Integration**.
4. Download **UK Gay Saunas & Events**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & services → Add integration** and choose **UK Gay Saunas & Events**.
7. Review the source URLs in the setup form. Enter one HTTPS directory URL per line. Existing installations keep their configured source list.

## Calendar and event accuracy

The scraper prefers dated structured event data and also attempts to interpret visible weekday schedules. Weekly schedules are expanded into future occurrences and ordinal monthly schedules into matching dates. Some sites load events with JavaScript, block automated requests, or publish vague schedules; those events may not be detected.

For Number 52 in Newcastle, the integration also checks its dedicated events page. If the page contains no extractable dated events, the integration may show inferred occurrences for the publicly listed recurring Thursday nights. These are labelled as inferred and should be confirmed with the venue before travelling. Rotating or one-off events are not guessed.

All scraped and inferred event dates are best-effort. Check the venue's official website before travelling, especially around holidays or schedule changes. Respect source website terms and rate limits.

## Entities

- **Events calendar**: upcoming events with venue, location, price, description and source link where available.
- **Next event**: the next event matched to each venue.
- **Opening status**: calculated only when published opening hours can be parsed; otherwise reports `Not published`.
- **Pricing / Private rooms / Official website**: reports extracted information and source attributes when available.
- **Information button**: creates a persistent notification containing the venue link and matched upcoming events.
- **Favourite / Notifications switches**: save favourite venues and opt in to event reminders for a venue.
- **Directory crawl sensor**: exposes venue count, per-source crawl statistics, errors, total pages visited, event count and last update.

Home Assistant entity IDs can vary if another integration already uses a suggested ID. Venue-specific unique IDs are based on the venue URL rather than its position in a scraped list.

## Troubleshooting

1. Open **Developer Tools → States** and find the `UKGA directory crawl` sensor.
2. Inspect `last_updated`, `total_events_found`, `regions` and `source_errors`.
3. Check the Home Assistant logs for `ukga` errors.
4. Open the relevant official venue website and compare the extracted events with its current published schedule.

A successful crawl does not guarantee that every website exposes its event details as ordinary HTML. The integration should report source failures rather than treating an inaccessible source as proof that no events exist.

## Development and testing

Run the pure scraper regression tests with:

```bash
python -m pip install pytest
python -m pytest -q
python -m compileall -q custom_components/ukga
```

The integration has not been executed in a live Home Assistant instance as part of this change. Automated unit tests can verify parser behavior, but runtime compatibility and all live venue pages still need validation.
