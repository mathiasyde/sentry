// browser: asks the in-page observer to wrap one sensitive bridge method; returns false if the observer is missing.
(function() {
  const state = window[__SENTRY_NAMESPACE__];
  if (!state || typeof state.wrapBridgeMethod !== "function") {
    return false;
  }
  return state.wrapBridgeMethod(
    __SENTRY_INTERFACE_NAME__,
    __SENTRY_METHOD_NAME__,
    __SENTRY_SOURCE__
  );
})();
