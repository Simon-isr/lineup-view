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

// Label this visit with whatever username was typed into the Basic Auth
// prompt (see server.py's BasicAuthMiddleware) -- not a verified identity,
// just enough to tell "who's using this" apart in GA instead of anonymous
// session IDs. No-ops locally (no APP_PASSWORD -> no Authorization header).
fetch("/api/whoami")
  .then((r) => (r.ok ? r.json() : null))
  .then((data) => {
    if (data && data.app_user && typeof gtag === "function") {
      gtag("set", "user_properties", { app_user: data.app_user });
    }
  })
  .catch(() => {});
