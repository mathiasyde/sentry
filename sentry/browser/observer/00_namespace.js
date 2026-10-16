// browser: installs the in-page observer once per page: per-run namespace, shared state and event buffer.
  const namespace = __SENTRY_NAMESPACE__;
  if (window[namespace] && window[namespace].version) { return true; }

  const state = {
    version: 1,
    events: [],
    taints: [],
    taintByValue: {},
    taintedStorage: {},
    bridgeWrappers: {},
  };

  Object.defineProperty(window, namespace, {
    value: state,
    configurable: false,
    enumerable: false,
    writable: false,
  });
