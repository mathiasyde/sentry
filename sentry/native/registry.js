// native: per-run WebView registry (ids, URLs, settings and bridge maps) and shared Java hooking helpers.
function createRegistry() {
  let nextWebViewId = 1;
  const webViews = {};
  const settingsToWebView = {};
  const bridgeObjects = {};
  const webViewsById = {};
  const bridgeTaintWrappersByWebView = {};
  const hookedBridgeMethods = {};
  const hookedWebViewClientClasses = {};
  const hookedWebChromeClientClasses = {};

  const keyFor = (object) => {
    if (object === null || object === undefined) return "null";
    try {
      return `${object.$className || "java.lang.Object"}:${object.hashCode()}`;
    } catch (e) {
      return object.toString();
    }
  };

  const classNameOf = (object) => {
    try {
      return object.getClass().getName().toString();
    } catch (e) {
      return object.$className || object.toString();
    }
  };

  const stringValue = (value) => {
    if (value === null || value === undefined) return null;
    try {
      return value.toString();
    } catch (e) {
      return String(value);
    }
  };

  const originForUrl = (url) => {
    if (!url) return null;

    const text = stringValue(url);
    const match = /^([a-zA-Z][a-zA-Z0-9+.-]*):(?:\/\/([^/?#]*))?/.exec(text);
    if (!match) return null;

    const scheme = match[1].toLowerCase();
    const authority = match[2];

    if (scheme === "http" || scheme === "https") {
      return authority ? `${scheme}://${authority}` : `${scheme}:`;
    }

    return `${scheme}:`;
  };

  const getWebViewState = (view) => {
    const key = keyFor(view);
    if (!webViews[key]) {
      webViews[key] = {
        id: nextWebViewId++,
        key: key,
        view: Java.retain(view),
        lastUrl: null,
        lastOrigin: null,
      };
      webViewsById[webViews[key].id] = webViews[key];
    }
    return webViews[key];
  };

  const updateWebViewUrl = (view, url) => {
    const state = getWebViewState(view);
    if (url !== null && url !== undefined) {
      state.lastUrl = stringValue(url);
      state.lastOrigin = originForUrl(state.lastUrl);
    }
    return state;
  };

  const registerSettings = (view, settings) => {
    const state = getWebViewState(view);
    settingsToWebView[keyFor(settings)] = state.id;
    return state;
  };

  const extractRequestUrl = (request) => {
    if (request === null || request === undefined) return null;
    try {
      const uri = request.getUrl();
      return uri ? uri.toString() : null;
    } catch (e) {
      return stringValue(request);
    }
  };

  const hookMethod = (clazz, methodName, argTypes, implementationFactory) => {
    if (!clazz[methodName]) return false;

    try {
      const overload = clazz[methodName].overload.apply(
        clazz[methodName],
        argTypes,
      );
      overload.implementation = implementationFactory(overload);
      return true;
    } catch (e) {
      return false;
    }
  };

  return {
    webViews,
    settingsToWebView,
    bridgeObjects,
    webViewsById,
    bridgeTaintWrappersByWebView,
    hookedBridgeMethods,
    hookedWebViewClientClasses,
    hookedWebChromeClientClasses,
    keyFor,
    classNameOf,
    stringValue,
    originForUrl,
    getWebViewState,
    updateWebViewUrl,
    registerSettings,
    extractRequestUrl,
    hookMethod,
  };
}
