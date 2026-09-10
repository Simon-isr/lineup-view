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

// The app has no login, so "who's using this" is just whichever Sleeper
// username someone typed in and loaded -- called from app.js/dashboard.js's
// fetchAndRender on every successful load, so it labels the whole session
// (all events, not just that one load) in GA.
function identifyVisitor(sleeperUsername) {
  try {
    if (typeof gtag === "function" && sleeperUsername) {
      gtag("set", "user_properties", { app_user: sleeperUsername });
    }
  } catch (e) {
    // analytics should never break the app
  }
}
