# Contract: browser-side scripts

Everything under `sentry/browser/` runs **inside the WebView page**. It must not reference `Java`, the event vocabulary, Frida APIs or any native module (FR-008, FR-012).

## Scripts

`native/browser_delivery.js` delivers these scripts by calling `renderBrowserScript(name, values)` and passing the result to `WebView.evaluateJavascript`.

| Name (`BROWSER_SOURCES` key) | Files | Placeholders | Returns (page-side) |
|---|---|---|---|
| `observer` | `browser/observer/00_namespace.js` … `50_bridge_wrapper.js`, concatenated inside one `(function(){ … })();` | `__SENTRY_NAMESPACE__` | `true`, both when it installs and when it is already installed |
| `bridgeTaint` | `browser/bridge_taint.js` | `__SENTRY_NAMESPACE__`, `__SENTRY_INTERFACE_NAME__`, `__SENTRY_METHOD_NAME__`, `__SENTRY_SOURCE__` | `false` if the observer is missing, otherwise the result of `state.wrapBridgeMethod(...)` |
| `probe` | `browser/probe.js` | `__SENTRY_NAMESPACE__`, `__SENTRY_WEBVIEW_ID__` | a JSON string (shape below) |

## Placeholder rendering

- Each placeholder is a bare identifier, so the source files stay valid JS.
- At render time, every occurrence of the token is replaced by `JSON.stringify(value)`. This is the same encoding the legacy template strings used.
- `__SENTRY_NAMESPACE__` is generated once per agent start as `"__sentry_webview_" + Math.random().toString(36).slice(2)`, exactly as before.
- Rendering fails, through a `js.probe.error` event, if any `__SENTRY_*__` token is left unreplaced.

## Page-side state (the API surface between the fragments and the native side)

```text
window[namespace] = {           // non-enumerable, non-writable, non-configurable
  version: 1,
  events: [],                   // ≤ 500, oldest dropped
  taints: [],                   // ≤ 200
  taintByValue: {}, taintedStorage: {}, bridgeWrappers: {},
  wrapBridgeMethod(interfaceName, methodName, source) -> bool
}
```

The intercepted page APIs must stay the same:
- `fetch`, `window.open`, `window.postMessage`, `navigator.sendBeacon`;
- `Location.prototype` `assign` and `replace`;
- `XMLHttpRequest.prototype` `open` and `send`;
- `Storage.prototype` `setItem` and `getItem`, with taint propagation;
- plus whatever else the legacy script intercepts. The [parity test](../research.md#r7-checking-browser-side-parity-without-a-device) is the authority.

## Probe result shape

```text
{ webViewId, href, injected: bool, events: [ {timestamp, name, arguments, ...} ], error?: string }
```

The native side unwraps the doubly-encoded `evaluateJavascript` value with `unwrapEvaluateJavascriptValue`, which moves to `browser_delivery.js`. It then emits one `js.probe` event for each page event.

## Delivery triggers (unchanged)

The observer and the bridge-taint wrappers are (re)delivered:
- on `onPageFinished` and `onLoadResource`;
- after each `loadUrl`, `postUrl`, `loadData` and `loadDataWithBaseURL` hook;
- on every poll tick (every 1000 ms), followed by the probe.
