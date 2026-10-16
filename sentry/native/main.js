// native: agent entry point: builds the shared context, installs every hook family in the legacy order,
// then polls WebViews and flushes events once per tick.
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

  const ctx = {
    WebView,
    WebViewClient,
    WebChromeClient,
    WebSettings,
    PermissionRequest,
    ValueCallback,
    StringClass,
    Modifier,
    JavascriptInterface,
    log,
  };
  Object.assign(ctx, createRegistry());
  Object.assign(ctx, createDelivery(ctx));
  Object.assign(ctx, createClientHookers(ctx));

  installBaseClientHooks(ctx);
  installWebViewConstructionHooks(ctx);
  installWebViewClientHooks(ctx);
  installWebViewLoadHooks(ctx);
  installJavascriptEvaluationHooks(ctx);
  installJavascriptBridgeHooks(ctx);
  installWebViewSettingsHooks(ctx);
  installPermissionHooks(ctx);
  installStaticBridgeHooks(ctx);

  setInterval(() => {
    ctx.retryStaticBridgeHooks();
    ctx.pollAll();

    flush();
  }, PROBE_POLLING_RATE);
});
