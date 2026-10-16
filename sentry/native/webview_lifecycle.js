// native: WebView lifecycle and navigation hooks: constructors, getSettings and the load*/postUrl methods.
function installWebViewConstructionHooks(ctx) {
  const {
    WebView,
    getWebViewState,
    registerSettings,
    log,
  } = ctx;

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
}

function installWebViewLoadHooks(ctx) {
  const {
    WebView,
    getWebViewState,
    updateWebViewUrl,
    stringValue,
    inject,
    injectBridgeTaintWrappers,
    log,
  } = ctx;

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
}
