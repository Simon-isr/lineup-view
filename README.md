# Lineup View

Enter a Sleeper username (or `user_id`) and see every roster you're on across
**every league you're in this season** (discovered live from Sleeper — no
per-league config to maintain, so a new league you join just shows up), each
one paired against that week's opponent. A "Playing now" toggle collapses it
to one flat view: your starters vs. their starters, only the ones currently
in a live NFL game.

## Run it

```bash
cd lineup-view
pip install -r requirements.txt
python -m uvicorn server:app --port 8779 --reload
```

Open http://localhost:8779/ — it auto-loads Simon's Sleeper username
(`SimonIsr`, hardcoded as `DEFAULT_USER` in `app.js`/`dashboard.js`) by
default; type a different one and hit Load to check someone else's leagues.

## Hosting it (so it works on any WiFi, not just home)

Deployed on [Render](https://render.com)'s free tier, from a **private**
repo under `github.com/Simon-isr` — a personal account with no Quandri org
membership, deliberately kept separate from work.

1. Render → New → Blueprint → point at the repo. `render.yaml` (committed)
   defines the whole service — no manual config beyond, optionally,
   `GA_MEASUREMENT_ID` (see "Analytics" below).
2. Open the `.onrender.com` URL Render gives you — no login, "Add to Home
   Screen" on your phone for an app-like icon.

**No password.** Used to gate the whole app behind HTTP Basic Auth
(`APP_PASSWORD`), removed once the app was meant for other people to
actually use — a shared login was friction, not security (anyone with the
URL only needed to make up a username anyway), and it also broke GA's own
tag-verification tool and any crawler, since they hit the 401 before ever
seeing the page. See "Analytics" below for how "who's using this" works
without it.

**Free-tier trade-offs, so they don't look like bugs later:**
- **Sleeps after ~15 min idle.** First request after a gap takes 30-60s to
  wake back up; normal after that.
- **Ephemeral disk.** `.cache/` resets on every redeploy/restart — harmless,
  it's just `sleeper.py`/`espn.py`'s perf cache, rebuilt on the next request.

## Analytics

Optional Google Analytics (GA4) — page views, time on site, and a handful of
click events (Load button, league tabs, each filter toggle, dashboard cards),
so it's visible whether anyone's actually using this beyond Simon.

1. Create a free GA4 property at [analytics.google.com](https://analytics.google.com)
   → Admin → Data Streams → add a Web stream → copy the **Measurement ID**
   (`G-XXXXXXXXXX`).
2. Set `GA_MEASUREMENT_ID` in Render's dashboard (kept out of git). Unset it
   and the pages load with no analytics script at all; nothing else changes.
3. Since there's no login to read a name from, `static/analytics.js` asks
   once per browser ("What's your name?"), stores the answer in
   `localStorage`, and sends it to GA as the `app_user` user property on
   every later visit from that browser/device. Declining leaves that visit
   anonymous in GA and asks again next time, rather than repeating a name
   it already has.

Privacy note: this sends visit + click data (not fantasy team data) to
Google. Fine for a tool shared with a few leaguemates; worth knowing if this
is ever opened up more broadly.

## How it works

- `sleeper.py` — vendored, minimal Sleeper API client (own cache under
  `.cache/`, not shared with `core/` or `league-commentator/lc/` — see their
  own VENDORED.md precedent for why a small forked client beats a
  cross-project import here).
- `espn.py` — a second, much smaller schedule source: ESPN's public
  scoreboard endpoint, used only for its kickoff timestamp (Sleeper's own
  schedule has a game *date* but no time-of-day). Live/final status still
  comes entirely from `sleeper.py` — see the "two schedule sources" note
  under Known assumptions for why they're not consolidated.
- `manual_leagues.json` — leagues on a platform not worth real integration
  for (currently: Quandri League, on ESPN). See "Manual leagues" below.
- `board.py` — the one real piece of logic: resolve the Sleeper id, discover
  every league via `/user/{id}/leagues/nfl/{season}` (not a static list),
  find your roster and this week's opponent in each, and flatten both sides
  into one list of "appearances" — `{league, side (mine/theirs), player,
  is_starter, is_live, points, ...}`. Both the per-league board and the
  "playing now" view are just filters over that same list (see the
  module docstring for why one shape, not two code paths).
- `server.py` — FastAPI, one endpoint (`/api/appearances`) + static files,
  plus injecting the GA snippet into `index.html`/`dashboard.html` when
  `GA_MEASUREMENT_ID` is set (see "Analytics" above). No auth — see "No
  password" under "Hosting it".
- `render.yaml` — the hosted deploy's service definition, committed so
  Render's Blueprint flow needs zero manual dashboard config beyond,
  optionally, the GA measurement ID.
- `static/` — vanilla HTML/JS/CSS, no build step. Deliberately dependency-free
  so it's trivial to drop into a WKWebView / Capacitor shell for an iOS
  wrapper later without a rewrite — see "Path to iOS" below.
  `analytics.js` is the one exception worth calling out: a thin `gtag()`
  wrapper shared by `app.js`/`dashboard.js` (see "Analytics" above).

## Pages

- `/` — the matchup views below.
- `/dashboard` — point-in-time summary: one card per league, your score now,
  projected end-of-week score, and who's left to play, vs. that week's
  opponent. A card's border goes green/red depending on who's ahead on
  projected score. Projected final = actual points for anyone whose game is
  done, else the larger of (points accrued live) or (that player's pre-kickoff
  weekly projection, in the scoring variant matching the league's own `rec`
  setting — half-PPR leagues get `pts_half_ppr`, etc., no scoring math done by
  hand). It's a simple heuristic, not a live win-probability model — see
  `board._team_summary`'s docstring. Pinned by `tests/test_dashboard.py`.
  Clicking a card jumps to `/` filtered to that league with "Active only"
  already on (`/?league=<id>&active=1` — read once on first load, then a
  plain reload/Load click goes back to "All leagues").

## Views (on `/`)

- **By league** (default) — your roster vs. that week's opponent, one card per
  league, filterable by the league tabs.
- **Playing now** — flattens to starters (or everyone, if "Active only" is off)
  currently in a live game, yours vs. theirs.
- **All players (tags)** — one "master matchup": every player *you* own across
  every league (left) vs. every player any of this week's *opponents* own
  across every league (right) — the merged, cross-league equivalent of the
  per-league board, ignoring the league tabs since that's the point. Each row
  carries a full-code pill (`LEG`, `DCM`, `VFFL`, `CL`, ...) per league on its
  own side, plus a one-letter pill per league where the *other* side has that
  player too. Sorted by same-side tag count first, total tag count as
  tiebreaker, then name — e.g. CeeDee Lamb owned in both Central Ledger and
  DCM shows `CL` `DCM` and sits at the top of Yours with the other 2-league
  players. Still shows this week's points (summed across leagues, broken out
  per-league in the tooltip).
- **Active only** / **Playing now only** compose with all views (e.g.
  "All players" + "Playing now" = your starters, tagged, currently live).
- **Sort by position** — a toggle, not a separate view: reorders whatever
  rows the other toggles already narrowed down to QB → RB → WR → TE → DEF →
  K, starters before bench within each position (same tiebreak the default
  order already uses). Composes with every other view, including "Group by
  game time" — each kickoff-window card inherits the position order from the
  flat "All players" list it's bucketed from, so a window's rows land
  QB → RB → WR → ... too, not re-sorted independently per window.
- **Group by game time** — a checkbox that only appears under "All players",
  since a per-league card or the flat live view has nothing to group. Splits
  the same Yours/Opponents tag rows into one card per kickoff window instead
  of one flat pair of columns. Boundaries aren't fixed slot names ("Thursday
  night", "Sunday morning", ...) — those don't hold up week to week (a Week 1
  opener can land on a Wednesday; Thanksgiving week has three separate
  Thursday windows) — the rule is just: sort every kickoff on screen, start a
  new group whenever the gap from the previous one exceeds an hour. Each
  group gets its own per-column Total (not one grand total) — the point of
  this view is "what am I getting out of the Sunday morning slate", not a
  season-long number the flat "All players" total already gives you.

Every row shows actual → projected (same blend as the dashboard, see
`board._blend_points`) side by side. Each column ends in a **Total** row:
in the by-league view that's the server's own authoritative per-team
score/projected (`lg.my`/`lg.opp` — always starters-only, unaffected by
"Active only"); in "All players" (flat or grouped by game time) it's a sum
of whatever's actually on screen (there's no single per-team score to reuse
there, since a player can belong to more than one league in that view).

## Manual leagues

For a league on a platform not worth wiring up real integration for (ESPN's
fantasy API needs per-league cookie auth, unlike Sleeper's fully public one —
same tradeoff `YAHOO_INTEGRATION.md` documents for Yahoo), `manual_leagues.json`
holds a hand-maintained roster instead. Currently: **Quandri League** (ESPN).

- **No live scoring.** `points`/`projected` are exactly whatever's in the
  file — refresh it by pasting an updated roster/projections screen and
  asking Claude to update the file (or edit it directly). Game status and
  kickoff time still come from the real NFL schedule automatically (same
  `schedule_by_team`/`kickoff_by_team` every Sleeper league uses), so the
  live dot and "Group by game time" bucketing stay accurate even between
  manual score refreshes.
- **Format:** `{"leagues": [{"league_id", "name", "opponent_name", "roster": [{"sleeper_id", "slot", "points", "projected"}, ...]}]}`.
  `sleeper_id` is looked up once (via `sleeper.get_players()`) so the name/
  position/team always match the rest of the app, and so the player merges
  into the right row in "All players" instead of showing as an unrelated
  duplicate of himself. `slot` of `BN`/`IR` means bench; anything else counts
  as a starter. `opponent_name: null` means the opponent's roster isn't
  tracked — the by-league card shows "vs Opponent" with an empty column
  rather than a real matchup.
- **No opponent roster.** Only your own side is tracked; add an
  `opponent_name` (and, if you ever want it, a mirrored roster with
  `"side": "theirs"` support in `board.py`) if that becomes worth it.

## Known assumptions (flag if wrong)

- **"Active players" = starters, not full roster.** The per-league board view
  shows your whole roster (bench dimmed); "Playing now" only ever shows
  starters, since bench points don't count. Toggle to "include bench" isn't
  built — say if you want it.
- **Live = not a known finished/pre-game status.** Sleeper's schedule status
  field is undocumented; `board.is_live()` denylists `pre_game`/`complete`/
  `final`/etc. rather than allowlisting `in_game`, so an unfamiliar status
  string (halftime, delayed) defaults to "live" instead of silently hiding a
  real game. Pinned in `tests/test_live_filter.py`.
- **Multi-league same-player collisions are shown, not merged.** In the
  by-league/live views he appears as a separate row per league. The "All
  players" view is the deliberate exception: it merges him into one row
  precisely so the cross-league overlap is visible as tags.
- **One-letter opponent tags use the league code's first letter**, so two
  league names sharing an initial would collide on the same letter. Not an
  issue with the current 4 leagues (VFFL/LEG/DCM/Central Ledger → V/L/D/C,
  all distinct) — worth a second glance if a 5th league joins.
- **"Opponent has him too" only checks your own current-week opponents**,
  not every roster in the league — that's the only opponent data the app
  already pulls, and matches "an opponent has that player" read literally.
- **Projected score doesn't re-project mid-game.** Once a player's game goes
  live, his contribution is `max(actual so far, pre-kickoff projection)` —
  it won't raise the projection further if he's on pace to beat it, only
  floor it at what's already accrued. A rough "roughly where this team
  lands" number, not a precise finish-line estimate.
- **Projection variant is picked from the league's `rec` setting only**
  (0 → std, 0.5 → half-PPR, 1.0 → full PPR). A league with other custom
  scoring (bonuses, TE premium, etc.) gets the closest of Sleeper's three
  variants, not an exact replica of its own settings.
- **Two schedule sources, on purpose.** Live/final status (`board.is_live()`,
  pinned by `tests/test_live_filter.py`) comes from `sleeper.py`'s schedule —
  the same feed that updates `players_points`, so its status is most likely
  to agree with the points on screen. Kickoff time (`espn.py`, used only for
  "Group by game time") comes from ESPN's scoreboard, since Sleeper's own
  schedule has no time-of-day. ESPN's payload does carry a live status too;
  deliberately not using it, to avoid a live dot disagreeing with Sleeper's
  own scoring feed by a few minutes. Say if you'd rather consolidate onto
  one source.
- **ESPN team codes are crosswalked, one entry.** ESPN's scoreboard uses the
  same abbreviations as Sleeper for every team except Washington (`WSH` vs.
  Sleeper's `WAS`) — verified against the full week 1 2026 slate (32/32
  teams matched). See `espn.ESPN_TO_SLEEPER`.
- **Kickoff grouping degrades to one ungrouped bucket, not a broken page,**
  if the ESPN call fails or times out (`board.py` catches and logs to
  stderr) — a missing kickoff time isn't worth the same "raise rather than
  serve stale" policy `sleeper.py` uses for live status.
- **A player with no resolvable kickoff (bye week, or an ESPN/team-code
  mismatch) gets its own "Kickoff time unknown" group**, sorted last —
  common from week 5 on with "Active only" off, not an edge case.

## Not built yet

- Yahoo Fantasy (Simon's 5th league, on a different provider) — explicitly
  deferred, see `YAHOO_INTEGRATION.md` for the researched integration plan
  if this comes back up.

- No auth/multi-user accounts — one Sleeper id per page load, kept in
  `localStorage` for convenience only.
- No push/auto-refresh during live games — reload the page or add a
  `setInterval` poll once this is confirmed useful.
- No iOS app. Path when you want one: this is already a plain JSON API +
  static frontend, so the fastest route is (a) a PWA (Add to Home Screen,
  zero extra code) for something today, or (b) wrap `static/` in Capacitor
  for a real App Store build later, pointed at a hosted copy of `server.py`.
  A native SwiftUI rewrite is the only path that requires re-doing the UI;
  the API underneath doesn't change either way.

## Verified against the live 2026 season (2026-09-06)

- 4 leagues discovered for `SimonIsr`: VFFL (pre_draft — correctly shows no
  roster), LEG, DCM, and **The Central Ledger** (new this season, not present
  in any of `core/leagues.py` / `lc/leagues.py` / `Dynasty Capital
  2026/DRAFT_TOOL_CONTEXT.md` — confirms discovery-by-user-id was the right
  call over a static league list).
- `players_points`/`starters` confirmed present on the real matchups payload
  — no scoring math needed.
- **Not yet verified**: the live-game filter end-to-end, since the 2026
  season hasn't kicked off (`season_start_date: 2026-09-09`). Logic is
  pinned by `tests/test_live_filter.py`; do a real check once Thursday's game
  is live.
- **Kickoff grouping verified against the real ESPN payload for weeks 1, 12,
  and 13** (2026-09-07): week 1 splits into the expected 6 windows (Wed/Thu/
  Sun early/Sun late/Sun night/Mon); week 12 (Thanksgiving) correctly keeps
  the three separate Thursday windows apart (10am/1:30pm/5:20pm PT) instead
  of chaining them into one group. ESPN team codes matched Sleeper's own
  schedule 32/32 (week 1) and 28/28 (week 13, byes accounted for).
