# OLX.ua apartment observer

Reads apartment listings from OLX.ua into SQLite and keeps every sighting, so prices can be
compared over time. Exports to CSV or Google Sheets.

## What it guarantees

1. **The price is the seller's.** Search results and JSON-LD convert every price to one currency:
   an ad for `59 900 $` appears there as `2 717 016 грн`, so its price would seem to change with
   the exchange rate. The price is read from the label on the ad's own page. An unknown label is
   never guessed.
2. **Nothing disappears silently.** A listing whose price cannot be read stays in the results with
   a named reason in `gaps`. A run cannot end as `done` with an unexplained missing price.
3. **An empty run is a failure**, and so is a run with over 20% gaps. The exit code is 0 only for
   a `done` run, and a failed run never replaces the exported data.
4. **A stop loses nothing.** Each page and price is committed as it is read. Ctrl-C, SIGTERM, a
   block or a crash leaves a closed run. After `kill -9`, the next run closes it.
5. **It stops when told to.** One request per second, `Retry-After` respected, immediate stop on
   401/403, and a stop after five unreadable ads in a row, which means the site has changed.

## How it works

```
search pages -> observations (committed per page)
ad pages     -> native price, or a named gap (committed per ad)
verdict      -> done | failed + reason
```

| File | Role |
| --- | --- |
| `parse.py` | pages to typed rows, using the JSON embedded in the page; no I/O |
| `fetch.py` | pacing, retries, when to stop |
| `browser.py` | plain headless Chromium; loads the document only, no scripts or images |
| `store.py`, `schema.sql` | SQLite, constraints, single-run lock |
| `scrape.py` | one run from start to verdict |
| `export.py`, `cli.py` | CSV, Google Sheets, command line |

`price_changes` compares each listing's last two sightings, not two runs: a listing that drops out
of search for a few days still yields its change when it returns. Changing the currency does not
count as a price change.

## Usage

Needs [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run playwright install chromium
uv run olx-scraper scrape --pages 2 --limit 70
uv run olx-scraper export listings --csv listings.csv
uv run olx-scraper export price-changes --csv changes.csv
```

For Google Sheets, install the extra, share the sheet with your service account, fill in `.env`
(see `.env.example`) and run:

```bash
uv sync --extra sheets
uv run --env-file .env olx-scraper export listings --sheet
```

The export overwrites the first tab in one call and trims the rest afterwards, so a failed write
leaves the old rows in place.

## Checks

```bash
uv run ruff check . && uv run mypy && uv run pytest
```

Tests do not contact OLX. Fixtures keep the recorded page structure with people, descriptions,
photos and real links removed. `test_browser.py` runs real Chromium against a local server.

## Limits

- OLX shows at most 25 search pages per query; use a narrower `--category` for more.
- Listings move between pages while they are read. Repeats are stored once, but a listing can be
  missed, so absence from a run does not mean it was removed.
- Seller names, phones, descriptions and photos are not collected.
- It only reads paths allowed by `robots.txt`. Check OLX's terms before using it.
- OLX can refuse automated browsers, and in November 2026 it answered with HTTP 403. The
  scraper then stops and marks the run as failed, without disguising itself.

## License

MIT

## About me

Hey, my name is Anastasiia, I am a Data Engineer. I'm open to feedback and would love to discuss
the architectural choices in this project: [LinkedIn](https://www.linkedin.com/in/anastasiia-kukhar-mm7mm1/).
