// native: evaluateJavascript hook; ignores Sentry's own scripts (they contain the per-run namespace).
function installJavascriptEvaluationHooks(ctx) {
  const {
    WebView,
    getWebViewState,
    stringValue,
    log,
  } = ctx;

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
}
