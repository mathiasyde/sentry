# Contract: the event vocabulary

The single source is `sentry/core/events/event_types.json` (FR-011). The bundler generates `EVENT_TYPE` for the agent from it, and `core.events.EventType` exposes the same values in Python. The wire strings must not change (FR-004).

```json
{
  "WEBVIEW_CREATED": "webview.created",
  "WEBVIEW_PAGE_LOADED": "webview.page.loaded",
  "WEBVIEW_ADDED": "webview.added",
  "WEBVIEW_CLIENT_SET": "webview.client.set",
  "WEBCHROME_CLIENT_SET": "webview.chrome_client.set",
  "WEBVIEW_SETTINGS_CHANGED": "webview.settings.changed",
  "URL_LOADED": "url.loaded",
  "JS_EVALUATED": "js.evaluated",
  "JS_PROBE": "js.probe",
  "JS_PROBE_ERROR": "js.probe.error",
  "BRIDGE_ADDED": "bridge.added",
  "BRIDGE_METHOD_CALLED": "bridge.method.called",
  "BRIDGE_METHOD_ADDED": "bridge.method.added",
  "PERMISSION_REQUESTED": "permission.requested",
  "PERMISSION_GRANT_CALLED": "permission.grant.called",
  "PERMISSION_DENY_CALLED": "permission.deny.called"
}
```

The key order is kept as it is in the legacy `EVENT_TYPE`.

## Payload fields by type (emitted today, must stay the same)

The table lists payload `data` keys. Values are passed through `sanitize()`: Java objects become `toString()`, circular references become `"[Circular]"`, and functions become `"[Function: name]"`.

| Type | Native family | Payload keys |
|---|---|---|
| `webview.created` | lifecycle | `webViewId`, `constructor`, `retval` |
| `webview.added` | lifecycle | `webViewId`, `settings` |
| `url.loaded` (`loadUrl`) | lifecycle | `webViewId`, `url`, `source`, `retval`, optional `additionalHttpHeaders` |
| `url.loaded` (`postUrl`) | lifecycle | `webViewId`, `url`, `source`, `postDataLength`, `retval` |
| `url.loaded` (`loadData`) | lifecycle | `webViewId`, `source`, `mimeType`, `encoding`, `dataLength`, `retval` |
| `url.loaded` (`loadDataWithBaseURL`) | lifecycle | `webViewId`, `source`, `baseUrl`, `historyUrl`, `mimeType`, `encoding`, `dataLength`, `retval` |
| `url.loaded` (client callbacks) | clients | `webViewId`, `url`, `source`, `clientClass`, `retval` |
| `webview.page.loaded` | clients | `webViewId`, `url`, `clientClass`, `retval` |
| `webview.client.set` / `webview.chrome_client.set` | clients | `webViewId`, `clientClass`, `retval` |
| `webview.settings.changed` | settings | `webViewId`, `setting`, `args`, `retval` |
| `js.evaluated` | evaluation | `webViewId`, `pageUrl`, `script`, `callback`, `retval` |
| `js.probe` | delivery (wraps page events) | `webViewId`, `href`, `name`, `arguments`, optional `taints`, `bridge` |
| `js.probe.error` | delivery / bridge | `error`, plus context. Delivery adds `webViewId` and either `purpose` or `href` and `raw`. Bridge hooks add `className`, `method`, `source`, optional `args`. |
| `bridge.added` | bridge | `webViewId`, `pageUrl`, `origin`, `attachedPageUrl`, `attachedOrigin`, `object`, `interfaceName`, `className`, `retval` |
| `bridge.method.added` | bridge | `webViewId`, `pageUrl`, `origin`, `interfaceName`, `className`, `method`, `args`, `sensitive` |
| `bridge.method.called` | bridge | `webViewId`, `pageUrl`, `attachedPageUrl`, `attachedOrigin`, `currentPageUrl`, `currentOrigin`, `interfaceName`, `className`, `methodName`, `methodArgs`, `args`, `retval`, optional `error` |
| `permission.requested` (`onPermissionRequest`) | permissions | `chromeClientClass`, `origin`, `resources` |
| `permission.requested` (geolocation) | permissions | `chromeClientClass`, `type: "geolocation"`, `origin`, `callback` |
| `permission.grant.called` / `permission.deny.called` | permissions | `origin`, `resources` |

Before implementation starts, the keys above must be checked against the legacy source, for example by grepping the `log(EVENT_TYPE.…)` calls. The live comparator in `tests/tools/compare_event_streams.py` is what actually enforces equivalence.

## Normalization for live comparison

These values vary between runs, so they are masked before comparing:
- `timestamp`;
- the random namespace (`__sentry_webview_*`);
- values based on `hashCode`, `<class>:<hash>`;
- `taint-<ms>-<n>` ids;
- `retval` values that are object identity strings.
