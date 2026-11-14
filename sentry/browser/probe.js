// browser: drains the in-page event buffer and returns it to native code as a JSON string.
(function() {
  try {
    const state = window[__SENTRY_NAMESPACE__];
    if (!state || !state.events) {
      return JSON.stringify({
        webViewId: __SENTRY_WEBVIEW_ID__,
        href: location.href,
        injected: false,
        events: [],
        error: "probe namespace is not installed"
      });
    }

    const events = state.events.slice();
    state.events.length = 0;

    return JSON.stringify({
      webViewId: __SENTRY_WEBVIEW_ID__,
      href: location.href,
      injected: true,
      events: events
    });
  } catch (e) {
    return JSON.stringify({
      webViewId: __SENTRY_WEBVIEW_ID__,
      href: String(location && location.href || ""),
      injected: false,
      events: [],
      error: String(e && (e.stack || e.message) || e)
    });
  }
})();
