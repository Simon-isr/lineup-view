// Start/sit advice: one card per league, built entirely from
// lg.lineup_recommendation (board.py + lineup.py already computed it server
// side -- see lineup.py's module docstring for the actual logic). Reuses
// /api/appearances rather than a second endpoint, same precedent as
// dashboard.js.
const $ = (sel) => document.querySelector(sel);
const DEFAULT_USER = "SimonIsr";

$("#user").value = localStorage.getItem("lineupview.user") || DEFAULT_USER;

$("#load").addEventListener("click", () => fetchAndRender("button"));
$("#user").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchAndRender("enter"); });

fetchAndRender("auto"); // auto-load on open now that there's always a default user

async function fetchAndRender(trigger = "manual") {
  const user = $("#user").value.trim();
  if (!user) return;
  trackEvent("load_start_sit", { trigger, sleeper_user: user });
  identifyVisitor(user);
  localStorage.setItem("lineupview.user", user);
  $("#content").innerHTML = `<p class="empty">Loading&hellip;</p>`;
  try {
    const res = await fetch(`/api/appearances?user=${encodeURIComponent(user)}`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || res.statusText);
    }
    render(await res.json());
  } catch (err) {
    $("#content").innerHTML = `<p class="empty">Error: ${escapeHtml(err.message)}</p>`;
  }
}

function render(data) {
  const content = $("#content");
  const cards = data.leagues.map(cardHtml).join("");
  content.innerHTML = `<p class="week-note">Week ${data.week}, ${data.season}</p>${cards}`;
}

function cardHtml(lg) {
  const rec = lg.lineup_recommendation;
  if (!rec || rec.slots.length === 0) {
    return `<div class="matchup">
      <h2>${escapeHtml(lg.name)}</h2>
      <p class="note">${escapeHtml(lg.note || "nothing to recommend this week")}</p>
    </div>`;
  }
  const rows = rec.slots.map(slotRowHtml).join("");
  const notes = rec.notes.length
    ? `<ul class="reco-notes">${rec.notes.map(n => `<li>${noteHtml(n)}</li>`).join("")}</ul>`
    : `<p class="note">Current lineup already matches the recommendation.</p>`;
  return `<div class="matchup">
    <h2>${escapeHtml(lg.name)}</h2>
    <div class="reco-table">
      <div class="reco-row reco-head">
        <span class="reco-slot">Slot</span>
        <span class="reco-current">Current</span>
        <span class="reco-recommended">Recommended</span>
      </div>
      ${rows}
    </div>
    ${notes}
  </div>`;
}

function slotRowHtml(s) {
  const cls = ["reco-row"];
  if (s.changed) cls.push("changed");
  if (s.locked) cls.push("locked");
  const lock = s.locked ? `<span class="reco-lock" title="Already kicked off -- Sleeper won't let this slot change">&#128274;</span>` : "";
  return `<div class="${cls.join(" ")}">
    <span class="reco-slot">${escapeHtml(s.slot)}${lock}</span>
    <span class="reco-current">${playerCellHtml(s.current)}</span>
    <span class="reco-recommended">${playerCellHtml(s.recommended)}</span>
  </div>`;
}

function playerCellHtml(p) {
  if (!p) return `<span class="reco-empty">&mdash;</span>`;
  const kickoff = p.kickoff ? `<span class="reco-kickoff">${escapeHtml(formatKickoff(p.kickoff))}</span>` : "";
  const proj = p.projected == null ? "" : `<span class="reco-proj">proj ${p.projected.toFixed(1)}</span>`;
  const flag = p.injury_status && !["Questionable", "Probable"].includes(p.injury_status)
    ? `<span class="reco-flag">${escapeHtml(p.injury_status)}</span>` : "";
  return `<span class="reco-name">${escapeHtml(p.name)}</span>
    <span class="reco-meta">${escapeHtml(p.pos)}${p.team ? " &middot; " + escapeHtml(p.team) : ""} ${proj} ${kickoff} ${flag}</span>`;
}

// "Start X", "Sit Y", and "Move Z from A to B" all read the same way in
// board.py/lineup.py's plain-text notes -- style Start/Sit vs. Move
// differently here (points decision vs. pure optionality) by sniffing the
// leading word rather than adding a note "type" field across the wire.
function noteHtml(note) {
  const cls = note.startsWith("Move") ? "note-move" : note.startsWith("Sit") ? "note-sit" : "note-start";
  return `<span class="${cls}">${escapeHtml(note)}</span>`;
}

function formatKickoff(iso) {
  const d = new Date(iso);
  const weekday = d.toLocaleDateString(undefined, { weekday: "short" });
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${weekday} ${time}`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
