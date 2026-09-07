# Yahoo Fantasy integration — deferred, not forgotten

Simon has one league on Yahoo Fantasy in addition to the 4 Sleeper leagues.
Explicitly deferred 2026-09-06 — this is the plan to pick up from, not a
prompt to re-research from scratch, if/when it comes back.

## Why it's not a quick add (researched 2026-09-06)

Unlike Sleeper's fully public, keyless REST API, Yahoo's Fantasy Sports API
requires OAuth2 **and** Yahoo no longer self-serves API credentials — you must
submit an access application at sports.yahoo.com/developer/access (personal/
single-league use is an accepted category) and wait for Yahoo to approve it
before you get a consumer key/secret at all. No published turnaround time.
**That approval is the real blocking dependency, and it's a calendar
dependency, not a build-time one** — worth submitting early if this is ever
picked up, independent of when the code gets written.

Once approved: one-time interactive browser OAuth2 login mints an access +
refresh token pair. Access tokens expire hourly; refresh tokens are long-lived
and renew silently (not officially documented by Yahoo, but consistently
reported) — so after that one login, it's not a recurring auth chore.

## Tooling

`yahoo_fantasy_api` (PyPI, actively maintained — 2.12.3 as of Apr 2026,
wraps `yahoo_oauth` for token handling) is the best-maintained option and
covers NFL. Alternatives: `yfpy` (explicit NFL support, some open issues re:
undocumented rate limits under heavy call volume) and `yahoofantasy`.

## What's available / known quirks

Rosters, scoreboard/matchups, team stats, standings, free agents — comparable
to what Sleeper provides. **Live/in-game scoring is provisional**: Yahoo's
own StatTracker may lag mid-game, and official scoring doesn't finalize until
~8am PT the next day. Matters for the "playing now" view specifically — a
Yahoo player's live points here would be softer/less trustworthy than a
Sleeper player's in the same view. No published numeric rate limit; ToS just
reserves the right to throttle "excessive" use and requires single-account
use + attribution ("Fantasy data provided by Yahoo Fantasy").

## Code-side estimate

Comparable in shape to `sleeper.py` (a client module), but Yahoo's response
shapes are more nested/idiosyncratic than Sleeper's flat JSON, so `board.py`'s
merge logic needs real mapping work, not a drop-in swap — realistically a
weekend of build time, separate from however long Yahoo's approval takes.

## If this gets picked up

1. Submit the Yahoo access application first — do this even before deciding
   to build, since it's the long pole.
2. Once approved, do the one-time OAuth browser login and persist the token
   file (`yahoo_oauth`/`yahoo_fantasy_api` handle refresh from there).
3. New `yahoo.py` client module, same shape as `sleeper.py` — cache policy,
   read-only, own `.cache/` subkey.
4. Extend `board.py`'s `build_appearances`/`build_dashboard`-equivalent logic
   to merge a Yahoo league's roster/matchup data into the same "appearances"
   shape everything else already uses — that's the real work, not the auth.
5. Flag Yahoo-sourced live scores as provisional in the UI (a small badge or
   note) given the next-day-finalization quirk above.
