// native: WebViewClient / WebChromeClient hooks: client setters, navigation callbacks and per-class hooking.
function createClientHookers(ctx) {
  const {
    hookMethod,
    updateWebViewUrl,
    extractRequestUrl,
    stringValue,
    hookedWebViewClientClasses,
    hookedWebChromeClientClasses,
    inject,
    injectBridgeTaintWrappers,
    log,
  } = ctx;

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

    hookChromeClientPermissions(ctx, ChromeClientClass, className);
  };

  return {
    hookWebViewClientClass,
    hookWebChromeClientClass,
  };
}

function installBaseClientHooks(ctx) {
  const {
    hookWebViewClientClass,
    hookWebChromeClientClass,
  } = ctx;

  hookWebViewClientClass("android.webkit.WebViewClient");
  hookWebChromeClientClass("android.webkit.WebChromeClient");
}

function installWebViewClientHooks(ctx) {
  const {
    WebView,
    getWebViewState,
    classNameOf,
    hookWebViewClientClass,
    hookWebChromeClientClass,
    log,
  } = ctx;

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
}
