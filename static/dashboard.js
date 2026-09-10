// Point-in-time dashboard: one card per league -- your score now, projected
// end-of-week score, and who's left to play -- vs. that week's opponent.
// Reuses /api/appearances (board.py already attaches my/opp/my_owner/opp_owner
// summaries to each league entry) rather than a second endpoint.
const $ = (sel) => document.querySelector(sel);
const DEFAULT_USER = "SimonIsr";

$("#user").value = localStorage.getItem("lineupview.user") || DEFAULT_USER;

$("#load").addEventListener("click", () => fetchAndRender("button"));
$("#user").addEventListener("keydown", (e) => { if (e.key === "Enter") fetchAndRender("enter"); });

// Cards are recreated on every render(), so delegate from the container
// instead of re-attaching a listener per card.
$("#content").addEventListener("click", (e) => {
  const card = e.target.closest(".dash-card");
  if (card) trackEvent("dashboard_card_click", { league_name: card.querySelector("h2")?.textContent || "" });
});

fetchAndRender("auto"); // auto-load on open now that there's always a default user

async function fetchAndRender(trigger = "manual") {
  const user = $("#user").value.trim();
  if (!user) return;
  trackEvent("load_dashboard", { trigger, sleeper_user: user });
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
  content.innerHTML = `<p class="week-note">Week ${data.week}, ${data.season}</p>
    <div class="dash-grid">${data.leagues.map(cardHtml).join("")}</div>`;
}

function cardHtml(lg) {
  if (!lg.my) {
    return `<div class="dash-card muted">
      <h2>${escapeHtml(lg.name)}</h2>
      <p class="note">${escapeHtml(lg.note || "no data this week")}</p>
    </div>`;
  }
  const mine = lg.my;
  const opp = lg.opp; // may be null (bye)
  const leading = opp ? mine.projected > opp.projected : null;
  const cardClass = leading === null ? "" : leading ? "winning" : "losing";
  // Clicking a card jumps to the matchups page filtered to this league with
  // "Active only" already on -- the dashboard is the point-in-time summary,
  // the matchups page is where you go to see the actual players behind it.
  const href = `/?league=${encodeURIComponent(lg.league_id)}&active=1`;

  return `<a class="dash-card ${cardClass}" href="${href}">
    <h2>${escapeHtml(lg.name)}</h2>
    <div class="dash-row">
      <div class="dash-side">
        <div class="dash-owner">${escapeHtml(lg.my_owner || "You")}</div>
        <div class="dash-score">${mine.score.toFixed(1)}</div>
        <div class="dash-proj">proj ${mine.projected.toFixed(1)}</div>
        ${yetToPlayHtml(mine)}
      </div>
      <div class="dash-vs">vs</div>
      <div class="dash-side">
        ${opp ? `
          <div class="dash-owner">${escapeHtml(lg.opp_owner || "Opponent")}</div>
          <div class="dash-score">${opp.score.toFixed(1)}</div>
          <div class="dash-proj">proj ${opp.projected.toFixed(1)}</div>
          ${yetToPlayHtml(opp)}
        ` : `<div class="dash-owner">&mdash;</div><p class="note">bye week</p>`}
      </div>
    </div>
  </a>`;
}

function yetToPlayHtml(side) {
  if (side.yet_to_play_count === 0) return `<div class="dash-ytp done">all played</div>`;
  const names = side.yet_to_play.slice(0, 3).join(", ");
  const more = side.yet_to_play_count > 3 ? ` +${side.yet_to_play_count - 3} more` : "";
  return `<div class="dash-ytp" title="${escapeHtml(side.yet_to_play.join(", "))}">
    ${side.yet_to_play_count} left to play: ${escapeHtml(names)}${escapeHtml(more)}
  </div>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
