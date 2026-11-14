// native: renders browser/ scripts with run-time values and delivers them into WebViews; parses probe results.
const PROBE_POLLING_RATE = 1000; // ms
const SENTRY_NAMESPACE =
  "__sentry_webview_" + Math.random().toString(36).slice(2);

function renderBrowserScript(name, values) {
  let script = BROWSER_SOURCES[name];
  Object.keys(values).forEach((key) => {
    script = script.split(key).join(JSON.stringify(values[key]));
  });
  if (/__SENTRY_[A-Z_]+__/.test(script)) {
    throw new Error("unrendered placeholder in " + name);
  }
  return script;
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

function createDelivery(ctx) {
  const {
    StringClass,
    ValueCallback,
    webViews,
    bridgeTaintWrappersByWebView,
    getWebViewState,
    log,
  } = ctx;

  const INJECTION = renderBrowserScript("observer", {
    __SENTRY_NAMESPACE__: SENTRY_NAMESPACE,
  });

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
        renderBrowserScript("bridgeTaint", {
          __SENTRY_NAMESPACE__: SENTRY_NAMESPACE,
          __SENTRY_INTERFACE_NAME__: wrapper.interfaceName,
          __SENTRY_METHOD_NAME__: wrapper.methodName,
          __SENTRY_SOURCE__: wrapper.source,
        }),
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

  const pollAll = () => {
      Java.scheduleOnMainThread(() => {
        Object.keys(webViews).forEach((key) => {
          const state = webViews[key];
          const view = state.view;

          inject(view);
          injectBridgeTaintWrappers(view);
          evaluateOnWebView(
            view,
            renderBrowserScript("probe", {
              __SENTRY_NAMESPACE__: SENTRY_NAMESPACE,
              __SENTRY_WEBVIEW_ID__: state.id,
            }),
            ProbeCallback.$new(),
            "probe",
          );
        });
      });
  };

  return {
    evaluateOnWebView,
    inject,
    injectBridgeTaintWrappers,
    ProbeCallback,
    pollAll,
  };
}
