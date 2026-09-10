// Thin wrapper around GA4's gtag(), shared by app.js and dashboard.js. Every
// call is defensive -- when GA_MEASUREMENT_ID isn't set (local dev, or the
// server didn't inject the snippet), `gtag` is never defined and this is a
// silent no-op rather than a console error.
function trackEvent(name, params) {
  try {
    if (typeof gtag === "function") gtag("event", name, params || {});
  } catch (e) {
    // analytics should never break the app
  }
}

// The app has no login, so "who's using this" has to come from asking --
// once, on whichever device/browser someone's on, then remembered locally.
// Declining (Cancel, or closing the prompt) just leaves them anonymous in GA
// and asks again next visit, rather than nagging with a value already known.
function labelVisitor() {
  if (typeof gtag !== "function") return; // no GA_MEASUREMENT_ID -> nothing to label
  let name = localStorage.getItem("lineupview.visitor_name");
  if (!name) {
    name = (window.prompt("What's your name? (lets Simon see who's using this -- optional)") || "").trim();
    if (name) localStorage.setItem("lineupview.visitor_name", name);
  }
  if (name) gtag("set", "user_properties", { app_user: name });
}
labelVisitor();
