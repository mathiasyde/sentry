// native: WebSettings setter hooks (JavaScript, file access, mixed content, Safe Browsing, ...).
function installWebViewSettingsHooks(ctx) {
  const {
    WebSettings,
    settingsToWebView,
    keyFor,
    log,
  } = ctx;

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
}
