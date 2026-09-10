const $ = (sel) => document.querySelector(sel);
const DEFAULT_USER = "SimonIsr";

let DATA = null;          // last /api/appearances response
let activeLeague = "all";  // "all" or a league_id

// Deep-link support: /?league=<id>&active=1 (from the dashboard) preselects
// a league tab and checks "Active only"; /?all=1&group=1 (or just visit
// /all-players -- see server.py) checks "All players" and "Group by game
// time" instead. Applied on the first load only -- a plain reload or
// re-Load click afterward goes back to the plain default view.
const _urlParams = new URLSearchParams(location.search);
const _initialLeague = _urlParams.get("league");
const _initialActive = _urlParams.get("active") === "1";
const _initialAllPlayers = _urlParams.get("all") === "1";
const _initialGroupByTime = _urlParams.get("group") === "1";
let _initialApplied = false;

function loadUser() {
  $("#user").value = localStorage.getItem("lineupview.user") || DEFAULT_USER;
}
loadUser();

$("#load").addEventListener("click", () => fetchAndRender("button"));
$("#user").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchAndRender("enter"); });

// Each toggle fires its own named event (rather than one generic "filter
// changed") so a GA report can tell which toggles people actually use.
function trackToggle(id) {
  return () => { trackEvent(`toggle_${id}`, { checked: $(`#${id}`).checked }); render(); };
}
$("#liveOnly").addEventListener("change", trackToggle("liveOnly"));
$("#activeOnly").addEventListener("change", trackToggle("activeOnly"));
$("#allPlayers").addEventListener("change", trackToggle("allPlayers"));
$("#sortByPosition").addEventListener("change", trackToggle("sortByPosition"));
$("#groupByTime").addEventListener("change", trackToggle("groupByTime"));

fetchAndRender("auto"); // auto-load on open now that there's always a default user

async function fetchAndRender(trigger = "manual") {
  const user = $("#user").value.trim();
  if (!user) return;
  trackEvent("load_lineup", { trigger, sleeper_user: user });
  identifyVisitor(user);
  localStorage.setItem("lineupview.user", user);
  $("#content").innerHTML = `<p class="empty">Loading&hellip;</p>`;
  try {
    const res = await fetch(`/api/appearances?user=${encodeURIComponent(user)}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    DATA = await res.json();
    if (!_initialApplied) {
      _initialApplied = true;
      if (_initialLeague && DATA.leagues.some(l => l.league_id === _initialLeague)) activeLeague = _initialLeague;
      if (_initialActive) $("#activeOnly").checked = true;
      if (_initialAllPlayers) $("#allPlayers").checked = true;
      if (_initialGroupByTime) $("#groupByTime").checked = true;
    } else {
      activeLeague = "all";
    }
    renderTabs();
    render();
  } catch (err) {
    $("#content").innerHTML = `<p class="empty">Error: ${escapeHtml(err.message)}</p>`;
  }
}

function renderTabs() {
  const nav = $("#leagueTabs");
  nav.innerHTML = "";
  const mk = (id, label) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.className = id === activeLeague ? "active" : "";
    b.addEventListener("click", () => {
      trackEvent("league_tab_click", { league_id: id, league_name: label });
      activeLeague = id;
      renderTabs();
      render();
    });
    nav.appendChild(b);
  };
  mk("all", "All leagues");
  for (const lg of DATA.leagues) {
    if (lg.status === "in_season" || lg.status === "complete") mk(lg.league_id, lg.name);
  }
}

function render() {
  if (!DATA) return;
  const liveOnly = $("#liveOnly").checked;
  const activeOnly = $("#activeOnly").checked;
  const allPlayers = $("#allPlayers").checked;
  const sortByPosition = $("#sortByPosition").checked;

  // The tag view is inherently cross-league (that's the whole point -- a
  // league tab would cap every player at one tag), so it ignores the tab bar.
  $("#leagueTabs").style.display = allPlayers ? "none" : "";
  // "Group by game time" only makes sense here -- the by-league and live
  // views are already one flat list each, nothing to bucket by kickoff.
  $("#groupByTimeLabel").style.display = allPlayers ? "" : "none";
  if (allPlayers) {
    const { mine, theirs, codeNameMap } = buildAllPlayersColumns(DATA.appearances, { liveOnly, activeOnly, sortByPosition });
    if ($("#groupByTime").checked) {
      renderPlayerTagViewGrouped(mine, theirs, codeNameMap, liveOnly, activeOnly);
    } else {
      renderPlayerTagView(mine, theirs, codeNameMap, liveOnly, activeOnly);
    }
    return;
  }

  const scoped = DATA.appearances.filter(a => activeLeague === "all" || a.league_id === activeLeague);
  if (liveOnly) {
    renderLiveView(scoped.filter(a => a.is_live && (!activeOnly || a.is_starter)), sortByPosition);
  } else {
    renderLeagueView(scoped, activeOnly, sortByPosition);
  }
}

function renderLiveView(rows, sortByPosition) {
  const mine = rows.filter(a => a.side === "mine");
  const theirs = rows.filter(a => a.side === "theirs");
  if (sortByPosition) {
    mine.sort(byPosition);
    theirs.sort(byPosition);
  }
  const content = $("#content");
  if (mine.length === 0 && theirs.length === 0) {
    content.innerHTML = `<p class="empty">Nobody in an active lineup slot is currently in a live game.</p>`;
    return;
  }
  content.innerHTML = `
    <div class="matchup">
      <h2>Playing now</h2>
      <div class="columns">
        <div class="column">
          <h3>Yours</h3>
          ${mine.map(rowHtml).join("") || `<p class="note">none live right now</p>`}
        </div>
        <div class="column">
          <h3>Opponents</h3>
          ${theirs.map(rowHtml).join("") || `<p class="note">none live right now</p>`}
        </div>
      </div>
    </div>`;
}

function renderLeagueView(rows, activeOnly, sortByPosition) {
  const byLeague = new Map();
  for (const a of rows) {
    if (!byLeague.has(a.league_id)) byLeague.set(a.league_id, []);
    byLeague.get(a.league_id).push(a);
  }
  const content = $("#content");
  content.innerHTML = "";

  for (const lg of DATA.leagues) {
    if (activeLeague !== "all" && activeLeague !== lg.league_id) continue;
    const group = byLeague.get(lg.league_id) || [];
    const card = document.createElement("div");
    card.className = "matchup";
    if (group.length === 0) {
      card.innerHTML = `<h2>${escapeHtml(lg.name)}</h2><p class="note">${escapeHtml(lg.note || "no matchup this week")}</p>`;
      content.appendChild(card);
      continue;
    }
    const scope = (a) => !activeOnly || a.is_starter;
    const sortFn = sortByPosition ? byPosition : starterFirst;
    const mine = group.filter(a => a.side === "mine" && scope(a)).sort(sortFn);
    const theirs = group.filter(a => a.side === "theirs" && scope(a)).sort(sortFn);
    const owner = group.find(a => a.side === "mine")?.owner_name || "Me";
    const opp = group.find(a => a.side === "mine")?.opponent_name || "Opponent";
    // Totals are the server's own authoritative per-team score/projected
    // (board.py's _team_summary) -- always starters-only, regardless of the
    // "Active only" toggle, since a team's real score never includes bench.
    const mineTotal = lg.my ? totalRowHtml("Total", lg.my.score, lg.my.projected) : "";
    const oppTotal = lg.opp ? totalRowHtml("Total", lg.opp.score, lg.opp.projected) : "";
    card.innerHTML = `
      <h2>${escapeHtml(lg.name)} &mdash; ${escapeHtml(owner)} vs ${escapeHtml(opp)}</h2>
      <div class="columns">
        <div class="column"><h3>${escapeHtml(owner)}</h3>${mine.map(rowHtml).join("") || `<p class="note">none</p>`}${mineTotal}</div>
        <div class="column"><h3>${escapeHtml(opp)}</h3>${theirs.map(rowHtml).join("") || `<p class="note">none</p>`}${oppTotal}</div>
      </div>`;
    content.appendChild(card);
  }
}

// ---- All-players tag view ----
// One "master matchup": every player YOU own across every league (left) vs.
// every player any of THIS WEEK'S OPPONENTS own across every league (right)
// -- the merged, cross-league equivalent of the per-league board, so there's
// one listing that has all the players instead of four separate cards.
//
// Each row's main pills are full short-codes for the leagues on ITS side
// (blue = you own him there, red = an opponent owns him there); a row also
// gets a one-letter pill per league where the OTHER side has him too, so a
// player mine in two leagues and also rostered by an opponent in a third
// shows blue-blue-red. Sorted by same-side tag count first (2 leagues beats
// 1, the literal ask), then combined tag count, then name. Still shows this
// week's points per league (summed for display, broken out in the tooltip
// since scoring settings can differ league to league).

const LEAGUE_STOPWORDS = new Set(["of", "the", "and", "for"]);

function leagueCode(name) {
  const cleaned = name.replace(/^\s*The\s+/i, "").trim();
  const words = cleaned.split(/\s+/).filter(w => w && !LEAGUE_STOPWORDS.has(w.toLowerCase()));
  if (words.length <= 1) return cleaned.slice(0, 4).toUpperCase();
  return words.map(w => w[0].toUpperCase()).join("");
}

function buildAllPlayersColumns(allAppearances, { liveOnly, activeOnly, sortByPosition }) {
  let pool = allAppearances;
  if (liveOnly) pool = pool.filter(a => a.is_live);
  if (activeOnly) pool = pool.filter(a => a.is_starter);

  const bySide = { mine: new Map(), theirs: new Map() };
  const codeNameMap = new Map(); // code -> full league name, for tooltips

  for (const a of pool) {
    const code = leagueCode(a.league_name);
    codeNameMap.set(code, a.league_name);
    const map = bySide[a.side];
    if (!map.has(a.player_id)) {
      map.set(a.player_id, {
        name: a.name, pos: a.pos, team: a.team, kickoff: a.kickoff,
        codes: new Set(), anyLive: false, pointsByCode: new Map(), projByCode: new Map(),
      });
    }
    const rec = map.get(a.player_id);
    rec.codes.add(code);
    rec.anyLive = rec.anyLive || a.is_live;
    rec.pointsByCode.set(code, (rec.pointsByCode.get(code) || 0) + (a.points || 0));
    rec.projByCode.set(code, (rec.projByCode.get(code) || 0) + (a.projected ?? a.points ?? 0));
  }

  function toRows(side) {
    const otherSide = bySide[side === "mine" ? "theirs" : "mine"];
    const rows = [];
    for (const [pid, rec] of bySide[side]) {
      const tags = [...rec.codes].sort();
      const otherCodes = otherSide.get(pid)?.codes;
      // one-letter cross tag -- collapses to the code's first letter, so two
      // league codes sharing an initial would collide; not an issue today
      // (V/L/D/C are distinct across the current 4 leagues).
      const crossTags = otherCodes ? [...new Set([...otherCodes].map(c => c[0]))].sort() : [];
      const totalPoints = [...rec.pointsByCode.values()].reduce((s, v) => s + v, 0);
      const totalProjected = [...rec.projByCode.values()].reduce((s, v) => s + v, 0);
      rows.push({
        player_id: pid, name: rec.name, pos: rec.pos, team: rec.team, kickoff: rec.kickoff,
        tags, crossTags, anyLive: rec.anyLive,
        totalPoints, totalProjected, pointsByCode: rec.pointsByCode, projByCode: rec.projByCode,
      });
    }
    rows.sort((a, b) =>
      (sortByPosition ? positionRank(a.pos) - positionRank(b.pos) : 0) ||
      b.tags.length - a.tags.length ||
      (b.tags.length + b.crossTags.length) - (a.tags.length + a.crossTags.length) ||
      a.name.localeCompare(b.name)
    );
    return rows;
  }

  return { mine: toRows("mine"), theirs: toRows("theirs"), codeNameMap };
}

function renderPlayerTagView(mine, theirs, codeNameMap, liveOnly, activeOnly) {
  const content = $("#content");
  if (mine.length === 0 && theirs.length === 0) {
    content.innerHTML = `<p class="empty">No players match this filter.</p>`;
    return;
  }
  const scopeLabel = activeOnly ? "active players" : "all players";
  const liveLabel = liveOnly ? " &mdash; playing now" : "";
  const mineTotal = mine.length ? totalRowHtml("Total", sumOf(mine, "totalPoints"), sumOf(mine, "totalProjected")) : "";
  const theirsTotal = theirs.length ? totalRowHtml("Total", sumOf(theirs, "totalPoints"), sumOf(theirs, "totalProjected")) : "";
  content.innerHTML = `
    <div class="matchup">
      <h2>${escapeHtml(scopeLabel)}${liveLabel}</h2>
      <div class="columns">
        <div class="column">
          <h3>Yours</h3>
          ${mine.map(r => tagRowHtml(r, codeNameMap, "mine", "opp")).join("") || `<p class="note">none</p>`}
          ${mineTotal}
        </div>
        <div class="column">
          <h3>Opponents</h3>
          ${theirs.map(r => tagRowHtml(r, codeNameMap, "opp", "mine")).join("") || `<p class="note">none</p>`}
          ${theirsTotal}
        </div>
      </div>
    </div>`;
}

// Grand total across every listed row in a column -- not a per-team score
// (a player can belong to more than one league here), just the sum of
// what's on screen. Shared by the flat and grouped tag views.
function sumOf(rows, key) {
  return rows.reduce((s, r) => s + r[key], 0);
}

// ---- All-players tag view, grouped by kickoff time ----
// Same "Yours vs. Opponents" tag rows as renderPlayerTagView, just bucketed
// into one card per kickoff window instead of one flat pair of columns.
// Boundaries come from the actual slate, not fixed slot names ("Thursday
// night", "Sunday morning", ...) -- those don't even hold up week to week
// (a Week 1 opener can be Wednesday; Thanksgiving week has three Thursday
// windows). The rule is just: sort every known kickoff, start a new group
// whenever the gap from the previous one exceeds an hour.

function renderPlayerTagViewGrouped(mine, theirs, codeNameMap, liveOnly, activeOnly) {
  const content = $("#content");
  if (mine.length === 0 && theirs.length === 0) {
    content.innerHTML = `<p class="empty">No players match this filter.</p>`;
    return;
  }
  const scopeLabel = activeOnly ? "active players" : "all players";
  const liveLabel = liveOnly ? " &mdash; playing now" : "";

  const groups = groupByKickoff(mine, theirs);
  const cards = groups.map(g => {
    const mineTotal = g.mine.length ? totalRowHtml("Total", sumOf(g.mine, "totalPoints"), sumOf(g.mine, "totalProjected")) : "";
    const theirsTotal = g.theirs.length ? totalRowHtml("Total", sumOf(g.theirs, "totalPoints"), sumOf(g.theirs, "totalProjected")) : "";
    return `
      <div class="matchup">
        <h2>${escapeHtml(g.label)}</h2>
        <div class="columns">
          <div class="column">
            <h3>Yours</h3>
            ${g.mine.map(r => tagRowHtml(r, codeNameMap, "mine", "opp")).join("") || `<p class="note">none</p>`}
            ${mineTotal}
          </div>
          <div class="column">
            <h3>Opponents</h3>
            ${g.theirs.map(r => tagRowHtml(r, codeNameMap, "opp", "mine")).join("") || `<p class="note">none</p>`}
            ${theirsTotal}
          </div>
        </div>
      </div>`;
  }).join("");

  content.innerHTML = `<p class="week-note">${escapeHtml(scopeLabel)}${liveLabel} &mdash; grouped by kickoff</p>${cards}`;
}

// Buckets both columns' rows together against ONE shared set of group
// boundaries (computed from the union of every kickoff on screen) so Yours
// and Opponents always line up on the same windows -- clustering each side
// separately would let the two columns disagree about where a window starts.
function groupByKickoff(mine, theirs) {
  const ONE_HOUR_MS = 60 * 60 * 1000;
  const epochs = [...new Set(
    [...mine, ...theirs].filter(r => r.kickoff).map(r => new Date(r.kickoff).getTime())
  )].sort((a, b) => a - b);

  // New group whenever the gap from the previous kickoff is over an hour --
  // the plain reading of "kickoffs more than an hour apart". A slate whose
  // kickoffs chain <=60min apart start to end would collapse into one group;
  // a real NFL week doesn't do that (Sunday's windows run ~3h apart).
  const buckets = [];
  let current = [];
  for (const e of epochs) {
    if (current.length && e - current[current.length - 1] > ONE_HOUR_MS) {
      buckets.push(current);
      current = [];
    }
    current.push(e);
  }
  if (current.length) buckets.push(current);

  const groupIndexByEpoch = new Map();
  buckets.forEach((epochsInGroup, idx) => {
    for (const e of epochsInGroup) groupIndexByEpoch.set(e, idx);
  });

  const groups = buckets.map(epochsInGroup => ({ label: formatKickoffGroupLabel(epochsInGroup), mine: [], theirs: [] }));
  // Bye weeks and any player whose team we couldn't resolve a kickoff for
  // (ESPN lookup failed, unmapped team code, ...) land here instead of
  // silently disappearing -- common from week 5 on, not an edge case.
  const unknown = { label: "Kickoff time unknown", mine: [], theirs: [] };

  const place = (rows, side) => {
    for (const r of rows) {
      if (!r.kickoff) { unknown[side].push(r); continue; }
      groups[groupIndexByEpoch.get(new Date(r.kickoff).getTime())][side].push(r);
    }
  };
  place(mine, "mine");
  place(theirs, "theirs");

  if (unknown.mine.length || unknown.theirs.length) groups.push(unknown);
  return groups;
}

function formatKickoffGroupLabel(epochsInGroup) {
  const weekday = new Date(epochsInGroup[0]).toLocaleDateString(undefined, { weekday: "long" });
  // Rendered in the browser's own local time zone (no server-side tz
  // handling needed) -- dedupe first since an early Sunday slate is several
  // games at the same or near-same time.
  const times = [...new Set(epochsInGroup.map(e =>
    new Date(e).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })
  ))];
  const timeLabel = times.length === 1 ? times[0] : `${times[0]}–${times[times.length - 1]}`;
  return `${weekday} ${timeLabel}`;
}

function tagRowHtml(r, codeNameMap, mainClass, crossClass) {
  const dot = r.anyLive ? `<span class="dot live"></span>` : `<span class="dot dead"></span>`;
  const mainTags = r.tags
    .map(c => `<span class="tag ${mainClass}" title="${escapeHtml(codeNameMap.get(c) || c)}">${escapeHtml(c)}</span>`)
    .join("");
  const crossOwner = mainClass === "mine" ? "Opponent" : "You";
  const crossTags = r.crossTags
    .map(letter => {
      const match = [...codeNameMap.entries()].find(([code]) => code[0] === letter);
      const title = match ? `${crossOwner} also has him in ${match[1]}` : `${crossOwner} also has him`;
      return `<span class="tag ${crossClass} cross" title="${escapeHtml(title)}">${escapeHtml(letter)}</span>`;
    })
    .join("");
  const pointsTitle = [...r.pointsByCode.entries()]
    .map(([c, p]) => `${c} ${p.toFixed(1)} (proj ${(r.projByCode.get(c) || 0).toFixed(1)})`)
    .join(", ");
  // Owned/faced in more than one league on this side -- break out each
  // league's actual score individually, since the total on the right merges
  // them and that's exactly the case where "what's it made of" matters.
  const breakdown = r.tags.length > 1
    ? `<div class="breakdown">${r.tags.map(c => `${escapeHtml(c)} ${(r.pointsByCode.get(c) || 0).toFixed(1)}`).join(" &middot; ")}</div>`
    : "";
  return `<div class="row">
    <span class="name">${dot}${escapeHtml(r.name)} <span class="pos">${escapeHtml(r.pos)}${r.team ? " &middot; " + escapeHtml(r.team) : ""}</span>
      <span class="tags">${mainTags}${crossTags}</span>
    </span>
    <span title="${escapeHtml(pointsTitle)}">${scoresHtml(r.totalPoints, r.totalProjected)}</span>
    ${breakdown}
  </div>`;
}

function starterFirst(a, b) {
  return (b.is_starter - a.is_starter) || (b.points - a.points);
}

// "Sort by position" toggle -- QB/RB/WR/TE/DEF/K, in that order, composed
// with whatever other filters (Active only, Playing now, All players, Group
// by game time) are already narrowing the row list; this only changes the
// order those rows land in, same as starterFirst does by default. Anything
// outside this list (a position string this app hasn't seen) sorts last
// rather than crashing or silently vanishing.
const POSITION_ORDER = ["QB", "RB", "WR", "TE", "DEF", "K"];

function positionRank(pos) {
  const idx = POSITION_ORDER.indexOf(pos);
  return idx === -1 ? POSITION_ORDER.length : idx;
}

function byPosition(a, b) {
  return (positionRank(a.pos) - positionRank(b.pos)) || (b.is_starter - a.is_starter) || (b.points - a.points);
}

function rowHtml(a) {
  const dot = a.is_live ? `<span class="dot live"></span>` : `<span class="dot dead"></span>`;
  const badge = activeLeague === "all" ? `<span class="badge">${escapeHtml(a.league_name)}</span>` : "";
  return `<div class="row${a.is_starter ? "" : " bench"}">
    <span class="name">${dot}${escapeHtml(a.name)} <span class="pos">${escapeHtml(a.pos)}${a.team ? " &middot; " + escapeHtml(a.team) : ""}</span>${badge}</span>
    ${scoresHtml(a.points, a.projected)}
  </div>`;
}

// Actual + projected, shared by every row style in this file so the two never
// drift out of alignment. `projected` may be undefined for rows that don't
// carry it (there are none today, but keeps this safe if that ever changes).
function scoresHtml(points, projected) {
  const proj = projected == null
    ? ""
    : `<span class="pts proj" title="projected final">${projected.toFixed(1)}</span>`;
  return `<span class="scores"><span class="pts">${(points ?? 0).toFixed(1)}</span>${proj}</span>`;
}

// Footer row for a column: sum of actual + sum of projected across whatever
// that column authoritatively totals to (see call sites -- either the
// server's own per-team total, or a sum of the rows actually on screen).
function totalRowHtml(label, points, projected) {
  return `<div class="row total">
    <span class="name">${escapeHtml(label)}</span>
    ${scoresHtml(points, projected)}
  </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
