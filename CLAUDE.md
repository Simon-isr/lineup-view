# CLAUDE.md — Lineup View

## What This Is

A fantasy football matchup viewer: enter a Sleeper username and see every
roster you're on across every league you're in this season, each paired
against that week's opponent, plus a "playing now" filter and a
point-in-time dashboard. See `README.md` for the full feature list (views,
manual leagues, known assumptions) — this file is deploy/ops context for
Claude, not a feature doc.

Owner: Simon Israel. Personal project, unrelated to Quandri work — hosted
under Simon's personal GitHub (`github.com/Simon-isr`), deliberately kept
separate. Built 2026-09-06/07, deployed to Render + wired to Google
Analytics 2026-09-09.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Backend | FastAPI (Python), single process, `uvicorn` |
| Frontend | Vanilla HTML/JS/CSS, no build step, no framework |
| Hosting | [Render](https://render.com) free tier, Blueprint deploy from `render.yaml` |
| Data sources | Sleeper's public API (`sleeper.py`), ESPN's public scoreboard (`espn.py`, kickoff times only) |
| Analytics | Google Analytics 4, `gtag.js`, injected server-side |

---

## How to Run

```bash
pip install -r requirements.txt
python -m uvicorn server:app --port 8779 --reload
```

Open `http://localhost:8779/` — auto-loads `DEFAULT_USER` (`SimonIsr`,
hardcoded in `app.js`/`dashboard.js`). No env vars required locally;
`GA_MEASUREMENT_ID` unset just means no analytics script gets injected.

---

## Deploying (Render)

Repo is already wired to Render via Blueprint (`render.yaml` defines the
whole service — build/start command, plan, env var keys). A push to
`master` auto-deploys.

**Gotcha hit 2026-09-09: `git push` failed with "repository not found"
even though `gh repo view` worked fine.** Cause: git's credential helper
wasn't using `gh`'s auth. Fix, once, per machine:
```bash
gh auth setup-git
```
If push ever mysteriously 404s on a repo `gh` can clearly see, this is why.

**Render dashboard env vars currently set:**
- `GA_MEASUREMENT_ID` — GA4 measurement ID (`G-XXXXXXXXXX`). Get it from
  analytics.google.com → Admin → Data Streams → the Web stream.
- `APP_PASSWORD` — **removed 2026-09-09, do not re-add.** See "Decisions
  Log" below for why. If it reappears in Render's dashboard it's stale and
  unused by the code.

**Render → New → Blueprint flow only lists repos the Render GitHub App has
access to.** If a repo doesn't show up, it's a GitHub App permissions
issue, not a Render issue — fix at github.com/settings/installations
(under the account that owns the repo) → Render → Configure → repository
access.

---

## Critical Patterns

- **No auth, on purpose.** There is no password/login. `BasicAuthMiddleware`
  existed briefly (2026-09-07 to 2026-09-09) and was removed — see Decisions
  Log. Don't re-add a login wall without checking with Simon first; it broke
  GA's own tag-verification tool and any crawler last time (401 before ever
  serving the page).
- **`manual_leagues.json` is gated to Simon only.** `board.py`'s
  `MANUAL_LEAGUES_OWNER = "simonisr"` — only loads Simon's hand-maintained
  ESPN league when the *Sleeper username typed into the app* resolves to
  `SimonIsr` (case-insensitive). This is unrelated to site auth (there is
  none) — it's purely "don't show my private league to other people using
  the tool." Don't remove this gate without confirming.
- **GA identity = whatever Sleeper username was typed into Load.** Not a
  login, not a stored name — `identifyVisitor()` in `analytics.js`, called
  every time `fetchAndRender()` succeeds. A prompt-based "what's your name"
  version existed briefly (2026-09-09) and was deliberately replaced with
  this — simpler, no interruption, matches what "who" actually means for
  this app (see Decisions Log).
- **GA snippet is server-injected, not hardcoded.** `server.py`'s
  `_ga_snippet()`/`_render_page()` swap a `<!--GA_SNIPPET-->` placeholder in
  `index.html`/`dashboard.html` for the real `<script>` block only when
  `GA_MEASUREMENT_ID` is set. Keeps local dev script-free with zero config.

---

## Data Flow

```
Sleeper API (rosters, matchups, projections, schedule)  ─┐
ESPN scoreboard API (kickoff times only)                 ├─→ board.py (build_appearances) ──→ lineup.py (recommend_lineup, per league)
manual_leagues.json (Simon's ESPN league, gated)         ─┘         │
                                                                     ▼
                                          server.py (/api/appearances, JSON)
                                                                     │
                                                                     ▼
                            static/app.js + dashboard.js + start-sit.js (fetch, filter, render)
                                                                     │
                                                                     ▼
                                            static/analytics.js → GA4 (gtag)
```

---

## Key Files

| File | What it does |
|------|-------------|
| `server.py` | FastAPI app: `/api/appearances`, GA snippet injection, `/all-players` redirect. No auth. |
| `board.py` | Core logic — resolves Sleeper id, discovers leagues, flattens rosters into one `appearances` list. |
| `lineup.py` | Start/sit recommendation engine — best-lineup + flex-slot-by-kickoff logic, called from `board.py`, surfaced on `/start-sit`. |
| `sleeper.py` / `espn.py` | Vendored API clients (rosters/scoring vs. kickoff time). |
| `manual_leagues.json` | Simon's hand-maintained ESPN roster (gated to `SimonIsr`, see above). |
| `render.yaml` | Render Blueprint service definition — committed, drives the whole deploy. |
| `static/analytics.js` | `trackEvent()` + `identifyVisitor()` — shared GA helpers for `app.js`/`dashboard.js`/`start-sit.js`. |
| `static/app.js` | `/` page — matchups, live view, all-players/tags view, deep-link handling. |
| `static/dashboard.js` | `/dashboard` page — point-in-time score/projection cards. |
| `static/start-sit.js` | `/start-sit` page — per-league current-vs-recommended lineup table + notes. |

---

## Common Operations

### Deploying a change
1. `git add -A && git commit -m "..."` then `git push origin master`.
2. If push fails with "repository not found", run `gh auth setup-git` once
   (see Gotcha above) and retry.
3. Render auto-deploys on push. Check the Render dashboard's deploy log if
   it doesn't show up within a minute or two.

### Changing/refreshing Simon's manual ESPN league
Edit `manual_leagues.json` directly (roster, points, projected) — see
README's "Manual leagues" section for the exact format.

### Checking analytics is working
1. `curl -s https://lineup-view.onrender.com/ | grep gtag` — confirms the
   snippet is actually injected (i.e. `GA_MEASUREMENT_ID` is set correctly
   on Render — double-check for typos/truncation, see Gotcha below).
2. GA4 → Realtime report while loading the site in a browser.

---

## Gotchas

- **`git push` needing `gh auth setup-git`** — see "Deploying" above.
- **A truncated `GA_MEASUREMENT_ID` silently breaks analytics with no error
  anywhere obvious.** Hit this 2026-09-09: Render had `G-CJ6H8RPN8` (missing
  the trailing `F` from the real `G-CJ6H8RPN8F`) — page loaded fine, GA's
  own tag-checker just reported "not detected." Always verify by curling the
  live site and grepping for the exact ID string, not just "is a value set."
- **Render's Blueprint repo picker only shows repos its GitHub App can see**
  — a missing repo is a GitHub App permissions problem, not a Render bug.
- **Render free tier sleeps after ~15 min idle** — first request after a gap
  takes 30-60s. Normal, not a bug.
- **`.cache/` (Sleeper/ESPN perf cache) is ephemeral** — resets on every
  redeploy/restart. Harmless, just rebuilds on next request.

---

## Decisions Log (append-only)

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-09-07 | Built the app; deployed to Render via Blueprint, gated behind `APP_PASSWORD` (HTTP Basic Auth) | Wanted it reachable off home WiFi without building a real login system |
| 2026-09-09 | Gated `manual_leagues.json` to Simon's Sleeper username (`simonisr`) only | It was showing Simon's private ESPN league roster to anyone else using the tool |
| 2026-09-09 | Added optional GA4 analytics (page views, time on site, click events on Load/tabs/toggles/dashboard cards) | Simon wanted to see who's using the app and what they're doing in it |
| 2026-09-09 | Removed `APP_PASSWORD`/`BasicAuthMiddleware` entirely | It wasn't real security (anyone could type any username to pass it), it was blocking Simon's own phone (cached creds masked this) and GA's tag-verification crawler (401 before ever seeing the page), and Simon wants people actually using this |
| 2026-09-09 | Added `/all-players` → redirects to `/?all=1&group=1` | Bookmarkable/typeable shortcut into the "All players (tags)" + "Group by game time" view, reusing the existing `?league=&active=1` deep-link pattern |
| 2026-09-09 | Replaced the one-time "what's your name?" `window.prompt()` for GA identity with `identifyVisitor()`, fed the Sleeper username typed into Load | Simon didn't want a prompt at all — "who" should just be whatever Sleeper username someone's looking up, tracked silently |
| 2026-09-10 | Added `/start-sit` (new `lineup.py` module + page), embedded as `lg.lineup_recommendation` on the existing `/api/appearances` response rather than a new endpoint | Simon wanted per-league start/sit advice, specifically: among flex-eligible starters, whoever plays *last* should sit in the flex slot (not a dedicated position slot) for max last-second optionality. Reuses the dashboard's own "no second endpoint" precedent. |

---

## What's Not Built Yet

- Yahoo Fantasy integration (see `YAHOO_INTEGRATION.md` for the researched plan).
- No real multi-user accounts — one Sleeper id per page load, `localStorage` only.
- No push/auto-refresh during live games.
- No iOS app (PWA "Add to Home Screen" works today; Capacitor wrap or native
  rewrite are the two paths discussed — see README's "Path to iOS").
- No ad monetization — discussed 2026-09-09, deliberately not pursued: too
  little traffic to matter, and the app would need to be public + on a real
  domain first anyway.
