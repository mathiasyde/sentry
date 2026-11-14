const PROBE_POLLING_RATE = 1000; // ms
const SENTRY_NAMESPACE =
  "__sentry_webview_" + Math.random().toString(36).slice(2);

const EVENT_TYPE = Object.freeze({
  WEBVIEW_CREATED: "webview.created",
  WEBVIEW_PAGE_LOADED: "webview.page.loaded",
  WEBVIEW_ADDED: "webview.added",
  WEBVIEW_CLIENT_SET: "webview.client.set",
  WEBCHROME_CLIENT_SET: "webview.chrome_client.set",
  WEBVIEW_SETTINGS_CHANGED: "webview.settings.changed",
  URL_LOADED: "url.loaded",
  JS_EVALUATED: "js.evaluated",
  JS_PROBE: "js.probe",
  JS_PROBE_ERROR: "js.probe.error",
  BRIDGE_ADDED: "bridge.added",
  BRIDGE_METHOD_CALLED: "bridge.method.called",
  BRIDGE_METHOD_ADDED: "bridge.method.added",
  PERMISSION_REQUESTED: "permission.requested",
  PERMISSION_GRANT_CALLED: "permission.grant.called",
  PERMISSION_DENY_CALLED: "permission.deny.called",
});

const SENSITIVE_BRIDGE_METHOD_RE =
  /(camera|photo|image|location|gps|contact|sms|phone|call|record|audio|microphone|mic|token|secret|password|cookie|session|credential|permission|file|read|write|delete|download|upload|device|imei|androidid|id)/i;

function buildInjectionScript() {
  const namespace = JSON.stringify(SENTRY_NAMESPACE);

  return `(function() {
    const namespace = ${namespace};
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

    function copyArg(arg, depth) {
      if (depth > 2) { return "[MaxDepth]"; }
      if (arg === null || arg === undefined) { return null; }
      const t = typeof arg;
      if (t === "string" || t === "number" || t === "boolean") {
        return arg;
      }
      if (t === "function") {
        return "[Function: " + (arg.name || "anonymous") + "]";
      }
      if (Array.isArray(arg)) {
        return arg.slice(0, 20).map(function (item) {
          return copyArg(item, depth + 1);
        });
      }
      if (t === "object") {
        const out = {};
        Object.keys(arg).slice(0, 20).forEach(function (key) {
          try {
            out[key] = copyArg(arg[key], depth + 1);
          } catch (e) {
            out[key] = "[Unserializable]";
          }
        });
        return out;
      }
      return String(arg);
    }

    function report(event) {
      state.events.push({
        timestamp: new Date().toISOString(),
        name: event.name,
        arguments: event.arguments || [],
      });

      if (state.events.length > 500) {
        state.events.splice(0, state.events.length - 500);
      }
    }

    function fingerprint(value) {
      if (value === null || value === undefined) { return null; }

      try {
        if (typeof value === "string") {
          return value.length ? value.slice(0, 512) : null;
        }
        if (typeof value === "number" || typeof value === "boolean") {
          return String(value);
        }
        const json = JSON.stringify(copyArg(value, 0));
        return json && json !== "null" ? json.slice(0, 512) : null;
      } catch (e) {
        return String(value).slice(0, 512);
      }
    }

    function rememberTaint(value, source) {
      const fp = fingerprint(value);
      if (!fp) { return null; }

      const taint = {
        id: "taint-" + Date.now() + "-" + state.taints.length,
        source: source,
        valuePreview: fp.slice(0, 120),
      };

      state.taints.push(taint);
      state.taintByValue[fp] = taint;

      if (state.taints.length > 200) {
        const removed = state.taints.splice(0, state.taints.length - 200);
        removed.forEach(function (item) {
          Object.keys(state.taintByValue).forEach(function (key) {
            if (state.taintByValue[key] === item) {
              delete state.taintByValue[key];
            }
          });
        });
      }

      return taint;
    }

    function findTaint(value) {
      const fp = fingerprint(value);
      if (fp && state.taintByValue[fp]) {
        return state.taintByValue[fp];
      }

      if (typeof value === "string") {
        for (const key in state.taintByValue) {
          if (key.length >= 8 && value.indexOf(key) !== -1) {
            return state.taintByValue[key];
          }
        }
      }

      if (Array.isArray(value)) {
        for (let i = 0; i < value.length; i++) {
          const taint = findTaint(value[i]);
          if (taint) { return taint; }
        }
      }

      if (value && typeof value === "object") {
        const keys = Object.keys(value).slice(0, 20);
        for (let i = 0; i < keys.length; i++) {
          let taint = null;
          try {
            taint = findTaint(value[keys[i]]);
          } catch (e) {
            taint = null;
          }
          if (taint) { return taint; }
        }
      }

      return null;
    }

    function taintsForArgs(args) {
      const taints = [];
      Array.prototype.slice.call(args).forEach(function (arg, index) {
        const taint = findTaint(arg);
        if (taint) {
          taints.push({
            argumentIndex: index,
            taintId: taint.id,
            source: taint.source,
            valuePreview: taint.valuePreview,
          });
        }
      });
      return taints;
    }

    function intercept(owner, property, name) {
      try {
        const original = owner && owner[property];
        if (typeof original !== "function" || original.__sentryWrapped) {
          return;
        }

        const wrapped = function() {
          const rawArgs = Array.prototype.slice.call(arguments);
          const args = rawArgs.map(function (arg) {
            return copyArg(arg, 0);
          });
          const taints = taintsForArgs(rawArgs);
          report({ name: name, arguments: args, taints: taints });
          return original.apply(this, arguments);
        };

        Object.defineProperty(wrapped, "__sentryWrapped", {
          value: true,
          configurable: false,
          enumerable: false,
          writable: false,
        });

        owner[property] = wrapped;
      } catch (e) {
        report({ name: "sentry.intercept.failed", arguments: [name, String(e)] });
      }
    }

    intercept(window, "fetch", "fetch");
    intercept(window, "eval", "eval");
    intercept(window, "open", "window.open");
    intercept(window, "postMessage", "window.postMessage");

    if (window.navigator) {
      intercept(window.navigator, "sendBeacon", "navigator.sendBeacon");
    }

    if (window.Location && Location.prototype) {
      intercept(Location.prototype, "assign", "location.assign");
      intercept(Location.prototype, "replace", "location.replace");
    }

    if (window.XMLHttpRequest && XMLHttpRequest.prototype) {
      intercept(XMLHttpRequest.prototype, "send", "XMLHttpRequest.send");
      intercept(XMLHttpRequest.prototype, "open", "XMLHttpRequest.open");
    }

    if (window.Storage && Storage.prototype) {
      const originalSetItem = Storage.prototype.setItem;
      const originalGetItem = Storage.prototype.getItem;

      if (typeof originalSetItem === "function" && !originalSetItem.__sentryWrapped) {
        Storage.prototype.setItem = function(key, value) {
          const taints = taintsForArgs(arguments);
          if (taints.length > 0) {
            state.taintedStorage[String(key)] = taints[0];
          }
          report({
            name: "localStorage.setItem",
            arguments: [copyArg(key, 0), copyArg(value, 0)],
            taints: taints,
          });
          return originalSetItem.apply(this, arguments);
        };
        Object.defineProperty(Storage.prototype.setItem, "__sentryWrapped", {
          value: true,
          configurable: false,
          enumerable: false,
          writable: false,
        });
      }

      if (typeof originalGetItem === "function" && !originalGetItem.__sentryWrapped) {
        Storage.prototype.getItem = function(key) {
          const result = originalGetItem.apply(this, arguments);
          const storedTaint = state.taintedStorage[String(key)];
          if (storedTaint && result !== null && result !== undefined) {
            rememberTaint(result, storedTaint.source);
          }
          report({
            name: "localStorage.getItem",
            arguments: [copyArg(key, 0)],
            taints: storedTaint ? [storedTaint] : [],
          });
          return result;
        };
        Object.defineProperty(Storage.prototype.getItem, "__sentryWrapped", {
          value: true,
          configurable: false,
          enumerable: false,
          writable: false,
        });
      }
    }

    state.wrapBridgeMethod = function(interfaceName, methodName, source) {
      const key = interfaceName + "." + methodName;
      if (state.bridgeWrappers[key]) { return true; }

      const bridge = window[interfaceName];
      if (!bridge || typeof bridge[methodName] !== "function") {
        return false;
      }

      const original = bridge[methodName];
      const wrapped = function() {
        const args = Array.prototype.slice.call(arguments).map(function (arg) {
          return copyArg(arg, 0);
        });
        const result = original.apply(this, arguments);
        const taint = rememberTaint(result, source);
        report({
          name: "bridge.method.return.tainted",
          arguments: args,
          taints: taint ? [{
            argumentIndex: -1,
            taintId: taint.id,
            source: taint.source,
            valuePreview: taint.valuePreview,
          }] : [],
          bridge: {
            interfaceName: interfaceName,
            methodName: methodName,
          },
        });
        return result;
      };

      Object.defineProperty(wrapped, "__sentryWrapped", {
        value: true,
        configurable: false,
        enumerable: false,
        writable: false,
      });

      try {
        bridge[methodName] = wrapped;
        state.bridgeWrappers[key] = true;
        return true;
      } catch (e) {
        report({
          name: "bridge.method.wrap.failed",
          arguments: [interfaceName, methodName, String(e)],
        });
        return false;
      }
    };

    return true;
  })();`;
}

function buildBridgeTaintScript(interfaceName, methodName, source) {
  return `(function() {
    const state = window[${JSON.stringify(SENTRY_NAMESPACE)}];
    if (!state || typeof state.wrapBridgeMethod !== "function") {
      return false;
    }
    return state.wrapBridgeMethod(
      ${JSON.stringify(interfaceName)},
      ${JSON.stringify(methodName)},
      ${JSON.stringify(source)}
    );
  })();`;
}

function buildProbeScript(webViewId) {
  const namespace = JSON.stringify(SENTRY_NAMESPACE);
  const id = JSON.stringify(webViewId);

  return `(function() {
    try {
      const state = window[${namespace}];
      if (!state || !state.events) {
        return JSON.stringify({
          webViewId: ${id},
          href: location.href,
          injected: false,
          events: [],
          error: "probe namespace is not installed"
        });
      }

      const events = state.events.slice();
      state.events.length = 0;

      return JSON.stringify({
        webViewId: ${id},
        href: location.href,
        injected: true,
        events: events
      });
    } catch (e) {
      return JSON.stringify({
        webViewId: ${id},
        href: String(location && location.href || ""),
        injected: false,
        events: [],
        error: String(e && (e.stack || e.message) || e)
      });
    }
  })();`;
}

// Safe serializer that handles circular refs and Frida Java proxies.
function sanitize(value, seen = new Set()) {
  if (value === null || value === undefined) return null;
  const t = typeof value;
  if (t === "string" || t === "number" || t === "boolean") return value;
  if (t === "function") return `[Function: ${value.name || "anonymous"}]`;
  if (seen.has(value)) return "[Circular]";
  if (Array.isArray(value)) {
    seen.add(value);
    const arr = value.map((v) => sanitize(v, seen));
    seen.delete(value);
    return arr;
  }
  if (t === "object") {
    if (value.$className) {
      try {
        return value.toString();
      } catch (e) {
        return `[Java object ${value.$className}]`;
      }
    }
    seen.add(value);
    const out = {};
    for (const k in value) {
      try {
        out[k] = sanitize(value[k], seen);
      } catch (e) {
        out[k] = "[Unserializable]";
      }
    }
    seen.delete(value);
    return out;
  }
  return String(value);
}

function unwrapEvaluateJavascriptValue(value) {
  if (value === null || value === undefined) return null;

  try {
    const outer = JSON.parse(value.toString());
    if (typeof outer === "string") {
      return JSON.parse(outer);
    }
    return outer;
  } catch (e) {
    return {
      injected: false,
      events: [],
      error: `failed to parse probe result: ${String(e)}`,
      raw: value.toString(),
    };
  }
}

Java.perform(() => {
  const WebView = Java.use("android.webkit.WebView");
  const WebViewClient = Java.use("android.webkit.WebViewClient");
  const WebChromeClient = Java.use("android.webkit.WebChromeClient");
  const WebSettings = Java.use("android.webkit.WebSettings");
  const PermissionRequest = Java.use("android.webkit.PermissionRequest");
  const ValueCallback = Java.use("android.webkit.ValueCallback");
  const StringClass = Java.use("java.lang.String");
  const Modifier = Java.use("java.lang.reflect.Modifier");
  const JavascriptInterface = Java.use("android.webkit.JavascriptInterface");

  const INJECTION = buildInjectionScript();

  let nextWebViewId = 1;
  const messages = [];
  const webViews = {};
  const settingsToWebView = {};
  const bridgeObjects = {};
  const webViewsById = {};
  const bridgeTaintWrappersByWebView = {};
  const hookedBridgeMethods = {};
  const hookedWebViewClientClasses = {};
  const hookedWebChromeClientClasses = {};

  const log = (type, data, timestamp = new Date().toISOString()) => {
    messages.push({ type: type, timestamp: timestamp, data: data });
  };

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

  const evaluateOnWebView = (view, script, callback, purpose) => {
    try {
      view.evaluateJavascript(StringClass.$new(script), callback);
      return true;
    } catch (e) {
      const state = getWebViewState(view);
      log(EVENT_TYPE.JS_PROBE_ERROR, {
        webViewId: state.id,
        purpose: purpose,
        error: String(e),
      });
      return false;
    }
  };

  const inject = (view) => {
    evaluateOnWebView(view, INJECTION, null, "inject");
  };

  const injectBridgeTaintWrappers = (view) => {
    const state = getWebViewState(view);
    const wrappers = bridgeTaintWrappersByWebView[state.id] || [];

    wrappers.forEach((wrapper) => {
      evaluateOnWebView(
        view,
        buildBridgeTaintScript(
          wrapper.interfaceName,
          wrapper.methodName,
          wrapper.source,
        ),
        null,
        "bridge-taint",
      );
    });
  };

  const ProbeCallback = Java.registerClass({
    name: "com.frida.instrumentation.ProbeCallback",
    implements: [ValueCallback],
    methods: {
      onReceiveValue: function (value) {
        const data = unwrapEvaluateJavascriptValue(value);
        if (!data) return;

        if (data.error) {
          log(EVENT_TYPE.JS_PROBE_ERROR, {
            webViewId: data.webViewId || null,
            href: data.href || null,
            error: data.error,
            raw: data.raw || null,
          });
        }

        if (!data.events || !data.events.forEach) return;

        data.events.forEach((event) => {
          log(
            EVENT_TYPE.JS_PROBE,
            {
              webViewId: data.webViewId || null,
              href: data.href || null,
              name: event.name,
              arguments: event.arguments,
              taints: event.taints || [],
              bridge: event.bridge || null,
            },
            event.timestamp,
          );
        });
      },
    },
  });

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

  const hookWebViewClientClass = (className) => {
    if (!className || hookedWebViewClientClasses[className]) return;
    hookedWebViewClientClasses[className] = true;

    let ClientClass = null;
    try {
      ClientClass = Java.use(className);
    } catch (e) {
      return;
    }

    hookMethod(
      ClientClass,
      "onPageFinished",
      ["android.webkit.WebView", "java.lang.String"],
      (overload) =>
        function (view, url) {
          const retval = overload.apply(this, arguments);
          const state = updateWebViewUrl(view, url);

          log(EVENT_TYPE.WEBVIEW_PAGE_LOADED, {
            webViewId: state.id,
            url: stringValue(url),
            clientClass: className,
            retval: retval,
          });

          inject(view);
          injectBridgeTaintWrappers(view);
          return retval;
        },
    );

    hookMethod(
      ClientClass,
      "onLoadResource",
      ["android.webkit.WebView", "java.lang.String"],
      (overload) =>
        function (view, url) {
          const retval = overload.apply(this, arguments);
          updateWebViewUrl(view, url);
          inject(view);
          injectBridgeTaintWrappers(view);
          return retval;
        },
    );

    hookMethod(
      ClientClass,
      "shouldOverrideUrlLoading",
      ["android.webkit.WebView", "java.lang.String"],
      (overload) =>
        function (view, url) {
          const retval = overload.apply(this, arguments);
          const state = updateWebViewUrl(view, url);

          log(EVENT_TYPE.URL_LOADED, {
            webViewId: state.id,
            source: "shouldOverrideUrlLoading",
            url: stringValue(url),
            clientClass: className,
            retval: retval,
          });

          return retval;
        },
    );

    hookMethod(
      ClientClass,
      "shouldOverrideUrlLoading",
      ["android.webkit.WebView", "android.webkit.WebResourceRequest"],
      (overload) =>
        function (view, request) {
          const retval = overload.apply(this, arguments);
          const url = extractRequestUrl(request);
          const state = updateWebViewUrl(view, url);

          log(EVENT_TYPE.URL_LOADED, {
            webViewId: state.id,
            source: "shouldOverrideUrlLoading",
            url: url,
            clientClass: className,
            retval: retval,
          });

          return retval;
        },
    );

    hookMethod(
      ClientClass,
      "shouldInterceptRequest",
      ["android.webkit.WebView", "java.lang.String"],
      (overload) =>
        function (view, url) {
          const retval = overload.apply(this, arguments);
          const state = updateWebViewUrl(view, url);

          log(EVENT_TYPE.URL_LOADED, {
            webViewId: state.id,
            source: "shouldInterceptRequest",
            url: stringValue(url),
            clientClass: className,
            retval: retval,
          });

          return retval;
        },
    );

    hookMethod(
      ClientClass,
      "shouldInterceptRequest",
      ["android.webkit.WebView", "android.webkit.WebResourceRequest"],
      (overload) =>
        function (view, request) {
          const retval = overload.apply(this, arguments);
          const url = extractRequestUrl(request);
          const state = updateWebViewUrl(view, url);

          log(EVENT_TYPE.URL_LOADED, {
            webViewId: state.id,
            source: "shouldInterceptRequest",
            url: url,
            clientClass: className,
            retval: retval,
          });

          return retval;
        },
    );
  };

  const hookWebChromeClientClass = (className) => {
    if (!className || hookedWebChromeClientClasses[className]) return;
    hookedWebChromeClientClasses[className] = true;

    let ChromeClientClass = null;
    try {
      ChromeClientClass = Java.use(className);
    } catch (e) {
      return;
    }

    hookMethod(
      ChromeClientClass,
      "onPermissionRequest",
      ["android.webkit.PermissionRequest"],
      (overload) =>
        function (request) {
          log(EVENT_TYPE.PERMISSION_REQUESTED, {
            chromeClientClass: className,
            origin: request ? stringValue(request.getOrigin()) : null,
            resources: request ? request.getResources() : [],
          });

          return overload.apply(this, arguments);
        },
    );

    hookMethod(
      ChromeClientClass,
      "onGeolocationPermissionsShowPrompt",
      ["java.lang.String", "android.webkit.GeolocationPermissions$Callback"],
      (overload) =>
        function (origin, callback) {
          log(EVENT_TYPE.PERMISSION_REQUESTED, {
            chromeClientClass: className,
            type: "geolocation",
            origin: stringValue(origin),
            callback: callback,
          });

          return overload.apply(this, arguments);
        },
    );
  };

  const hookBridgeMethod = (className, method, interfaceName, webViewId) => {
    const methodName = method.getName().toString();
    const parameterTypes = method.getParameterTypes();
    const methodArgs = [];

    for (let i = 0; i < parameterTypes.length; i++) {
      methodArgs.push(parameterTypes[i].getName().toString());
    }

    const signature = `${className}.${methodName}(${methodArgs.join(",")})`;
    const sensitive = SENSITIVE_BRIDGE_METHOD_RE.test(methodName);

    log(EVENT_TYPE.BRIDGE_METHOD_ADDED, {
      webViewId: webViewId,
      interfaceName: interfaceName,
      className: className,
      method: methodName,
      args: methodArgs,
      sensitive: sensitive,
      pageUrl: webViewsById[webViewId] ? webViewsById[webViewId].lastUrl : null,
      origin: webViewsById[webViewId]
        ? webViewsById[webViewId].lastOrigin
        : null,
    });

    if (sensitive) {
      if (!bridgeTaintWrappersByWebView[webViewId]) {
        bridgeTaintWrappersByWebView[webViewId] = [];
      }

      const wrapperKey = `${interfaceName}.${methodName}`;
      const exists = bridgeTaintWrappersByWebView[webViewId].some(
        (wrapper) => wrapper.key === wrapperKey,
      );

      if (!exists) {
        bridgeTaintWrappersByWebView[webViewId].push({
          key: wrapperKey,
          interfaceName: interfaceName,
          methodName: methodName,
          source: {
            kind: "javascript-bridge-return",
            interfaceName: interfaceName,
            methodName: methodName,
            className: className,
            sensitive: true,
          },
        });
      }
    }

    if (hookedBridgeMethods[signature]) return;
    hookedBridgeMethods[signature] = true;

    let BridgeClass = null;
    try {
      BridgeClass = Java.use(className);
    } catch (e) {
      log(EVENT_TYPE.JS_PROBE_ERROR, {
        source: "bridge.hook",
        className: className,
        method: methodName,
        error: String(e),
      });
      return;
    }

    try {
      const overload = BridgeClass[methodName].overload.apply(
        BridgeClass[methodName],
        methodArgs,
      );

      overload.implementation = function () {
        let retval = null;
        let threw = null;

        try {
          retval = overload.apply(this, arguments);
        } catch (e) {
          threw = e;
        }

        const bridge = bridgeObjects[keyFor(this)] || {};
        const webViewState = bridge.webViewId
          ? webViewsById[bridge.webViewId]
          : null;
        const currentPageUrl = webViewState
          ? webViewState.lastUrl
          : bridge.attachedPageUrl || null;
        const currentOrigin = webViewState
          ? webViewState.lastOrigin
          : bridge.attachedOrigin || null;

        log(EVENT_TYPE.BRIDGE_METHOD_CALLED, {
          webViewId: bridge.webViewId || null,
          attachedPageUrl: bridge.attachedPageUrl || null,
          attachedOrigin: bridge.attachedOrigin || null,
          currentPageUrl: currentPageUrl,
          currentOrigin: currentOrigin,
          pageUrl: currentPageUrl,
          interfaceName: bridge.interfaceName || interfaceName,
          className: className,
          methodName: methodName,
          methodArgs: methodArgs,
          args: Array.prototype.slice.call(arguments),
          retval: retval,
          error: threw ? String(threw) : null,
        });

        if (threw) throw threw;
        return retval;
      };
    } catch (e) {
      log(EVENT_TYPE.JS_PROBE_ERROR, {
        source: "bridge.hook",
        className: className,
        method: methodName,
        args: methodArgs,
        error: String(e),
      });
    }
  };

  const hookAllBridgeMethods = (object, interfaceName, webViewId) => {
    const className = classNameOf(object);
    const bridgeObject = Java.cast(object, Java.use(className));
    const methods = bridgeObject.class.getMethods();
    const seenMethods = {};

    for (let i = 0; i < methods.length; i++) {
      const method = methods[i];
      const methodKey = method.toString();

      if (seenMethods[methodKey]) continue;
      seenMethods[methodKey] = true;

      try {
        if (!Modifier.isPublic(method.getModifiers())) continue;
        if (!method.isAnnotationPresent(JavascriptInterface.class)) continue;
      } catch (e) {
        continue;
      }

      hookBridgeMethod(className, method, interfaceName, webViewId);
    }
  };

  hookWebViewClientClass("android.webkit.WebViewClient");
  hookWebChromeClientClass("android.webkit.WebChromeClient");

  WebView.$init.overloads.forEach((overload) => {
    overload.implementation = function () {
      const retval = overload.apply(this, arguments);
      const state = getWebViewState(this);

      try {
        WebView.setWebContentsDebuggingEnabled(true);
      } catch (e) {
        log(EVENT_TYPE.JS_PROBE_ERROR, {
          webViewId: state.id,
          source: "setWebContentsDebuggingEnabled",
          error: String(e),
        });
      }

      log(EVENT_TYPE.WEBVIEW_CREATED, {
        webViewId: state.id,
        constructor: overload.argumentTypes.map((arg) => arg.className),
        retval: retval,
      });

      return retval;
    };
  });

  WebView.getSettings.implementation = function () {
    const settings = this.getSettings();
    const state = registerSettings(this, settings);

    log(EVENT_TYPE.WEBVIEW_ADDED, {
      webViewId: state.id,
      settings: settings,
    });

    return settings;
  };

  WebView.setWebViewClient.overload(
    "android.webkit.WebViewClient",
  ).implementation = function (client) {
    const retval = this.setWebViewClient(client);
    const state = getWebViewState(this);
    const className = client ? classNameOf(client) : null;

    hookWebViewClientClass(className);

    log(EVENT_TYPE.WEBVIEW_CLIENT_SET, {
      webViewId: state.id,
      clientClass: className,
      retval: retval,
    });

    return retval;
  };

  WebView.setWebChromeClient.overload(
    "android.webkit.WebChromeClient",
  ).implementation = function (client) {
    const retval = this.setWebChromeClient(client);
    const state = getWebViewState(this);
    const className = client ? classNameOf(client) : null;

    hookWebChromeClientClass(className);

    log(EVENT_TYPE.WEBCHROME_CLIENT_SET, {
      webViewId: state.id,
      clientClass: className,
      retval: retval,
    });

    return retval;
  };

  WebView.loadUrl.overload("java.lang.String").implementation = function (url) {
    const retval = this.loadUrl(url);
    const state = updateWebViewUrl(this, url);
    inject(this);
    injectBridgeTaintWrappers(this);

    log(EVENT_TYPE.URL_LOADED, {
      webViewId: state.id,
      source: "loadUrl",
      url: stringValue(url),
      retval: retval,
    });

    return retval;
  };

  WebView.loadUrl.overload(
    "java.lang.String",
    "java.util.Map",
  ).implementation = function (url, additionalHttpHeaders) {
    const retval = this.loadUrl(url, additionalHttpHeaders);
    const state = updateWebViewUrl(this, url);
    inject(this);
    injectBridgeTaintWrappers(this);

    log(EVENT_TYPE.URL_LOADED, {
      webViewId: state.id,
      source: "loadUrl",
      url: stringValue(url),
      additionalHttpHeaders: additionalHttpHeaders,
      retval: retval,
    });

    return retval;
  };

  WebView.postUrl.overload(
    "java.lang.String",
    "[B",
  ).implementation = function (url, postData) {
    const retval = this.postUrl(url, postData);
    const state = updateWebViewUrl(this, url);
    inject(this);
    injectBridgeTaintWrappers(this);

    log(EVENT_TYPE.URL_LOADED, {
      webViewId: state.id,
      source: "postUrl",
      url: stringValue(url),
      postDataLength: postData ? postData.length : 0,
      retval: retval,
    });

    return retval;
  };

  WebView.loadData.overload(
    "java.lang.String",
    "java.lang.String",
    "java.lang.String",
  ).implementation = function (data, mimeType, encoding) {
    const retval = this.loadData(data, mimeType, encoding);
    const state = getWebViewState(this);
    inject(this);
    injectBridgeTaintWrappers(this);

    log(EVENT_TYPE.URL_LOADED, {
      webViewId: state.id,
      source: "loadData",
      mimeType: stringValue(mimeType),
      encoding: stringValue(encoding),
      dataLength: data ? data.length : 0,
      retval: retval,
    });

    return retval;
  };

  WebView.loadDataWithBaseURL.overload(
    "java.lang.String",
    "java.lang.String",
    "java.lang.String",
    "java.lang.String",
    "java.lang.String",
  ).implementation = function (baseUrl, data, mimeType, encoding, historyUrl) {
    const retval = this.loadDataWithBaseURL(
      baseUrl,
      data,
      mimeType,
      encoding,
      historyUrl,
    );
    const state = updateWebViewUrl(this, baseUrl || historyUrl);
    inject(this);
    injectBridgeTaintWrappers(this);

    log(EVENT_TYPE.URL_LOADED, {
      webViewId: state.id,
      source: "loadDataWithBaseURL",
      baseUrl: stringValue(baseUrl),
      historyUrl: stringValue(historyUrl),
      mimeType: stringValue(mimeType),
      encoding: stringValue(encoding),
      dataLength: data ? data.length : 0,
      retval: retval,
    });

    return retval;
  };

  WebView.evaluateJavascript.overload(
    "java.lang.String",
    "android.webkit.ValueCallback",
  ).implementation = function (script, callback) {
    const retval = this.evaluateJavascript(script, callback);
    const state = getWebViewState(this);
    const scriptText = stringValue(script) || "";

    if (scriptText.indexOf(SENTRY_NAMESPACE) === -1) {
      log(EVENT_TYPE.JS_EVALUATED, {
        webViewId: state.id,
        pageUrl: state.lastUrl,
        retval: retval,
        callback: callback,
        script: scriptText,
      });
    }

    return retval;
  };

  WebView.addJavascriptInterface.overload(
    "java.lang.Object",
    "java.lang.String",
  ).implementation = function (object, interfaceName) {
    const retval = this.addJavascriptInterface(object, interfaceName);
    const state = getWebViewState(this);
    const objectKey = keyFor(object);

    bridgeObjects[objectKey] = {
      webViewId: state.id,
      attachedPageUrl: state.lastUrl,
      attachedOrigin: state.lastOrigin,
      interfaceName: stringValue(interfaceName),
      className: classNameOf(object),
    };

    log(EVENT_TYPE.BRIDGE_ADDED, {
      webViewId: state.id,
      pageUrl: state.lastUrl,
      origin: state.lastOrigin,
      attachedPageUrl: state.lastUrl,
      attachedOrigin: state.lastOrigin,
      object: object,
      interfaceName: stringValue(interfaceName),
      className: classNameOf(object),
      retval: retval,
    });

    hookAllBridgeMethods(object, stringValue(interfaceName), state.id);

    return retval;
  };

  [
    "setJavaScriptEnabled",
    "setDomStorageEnabled",
    "setAllowFileAccess",
    "setAllowContentAccess",
    "setAllowFileAccessFromFileURLs",
    "setAllowUniversalAccessFromFileURLs",
    "setMixedContentMode",
    "setSafeBrowsingEnabled",
    "setDatabaseEnabled",
    "setGeolocationEnabled",
    "setJavaScriptCanOpenWindowsAutomatically",
  ].forEach((methodName) => {
    if (!WebSettings[methodName]) return;

    WebSettings[methodName].overloads.forEach((overload) => {
      overload.implementation = function () {
        const retval = overload.apply(this, arguments);
        const settingsKey = keyFor(this);

        log(EVENT_TYPE.WEBVIEW_SETTINGS_CHANGED, {
          webViewId: settingsToWebView[settingsKey] || null,
          setting: methodName,
          args: Array.prototype.slice.call(arguments),
          retval: retval,
        });

        return retval;
      };
    });
  });

  const permissionGrant = PermissionRequest.grant.overload(
    "[Ljava.lang.String;",
  );
  permissionGrant.implementation = function (resources) {
    log(EVENT_TYPE.PERMISSION_GRANT_CALLED, {
      origin: stringValue(this.getOrigin()),
      resources: resources,
    });

    return permissionGrant.apply(this, arguments);
  };

  const permissionDeny = PermissionRequest.deny.overload();
  permissionDeny.implementation = function () {
    log(EVENT_TYPE.PERMISSION_DENY_CALLED, {
      origin: stringValue(this.getOrigin()),
      resources: this.getResources(),
    });

    return permissionDeny.apply(this, arguments);
  };

  setInterval(() => {
    Java.scheduleOnMainThread(() => {
      Object.keys(webViews).forEach((key) => {
        const state = webViews[key];
        const view = state.view;

        inject(view);
        injectBridgeTaintWrappers(view);
        evaluateOnWebView(
          view,
          buildProbeScript(state.id),
          ProbeCallback.$new(),
          "probe",
        );
      });
    });

    messages.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    messages.forEach((message) => {
      console.log(JSON.stringify(sanitize(message)));
    });

    messages.length = 0;
  }, PROBE_POLLING_RATE);
});
