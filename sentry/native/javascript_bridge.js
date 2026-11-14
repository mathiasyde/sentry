// native: JavaScript bridge hooks: addJavascriptInterface and every exposed @JavascriptInterface method.
const SENSITIVE_BRIDGE_METHOD_RE =
  /(camera|photo|image|location|gps|contact|sms|phone|call|record|audio|microphone|mic|token|secret|password|cookie|session|credential|permission|file|read|write|delete|download|upload|device|imei|androidid|id)/i;

function installJavascriptBridgeHooks(ctx) {
  const {
    WebView,
    Modifier,
    JavascriptInterface,
    bridgeObjects,
    webViewsById,
    bridgeTaintWrappersByWebView,
    hookedBridgeMethods,
    keyFor,
    classNameOf,
    stringValue,
    getWebViewState,
    log,
  } = ctx;

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
}
