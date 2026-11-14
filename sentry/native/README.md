# native/

Frida hooks that run **in the app process** and intercept Android WebView APIs. Each API family has one module. Each module exposes `install…Hooks(ctx)` (or a `create…(ctx)` factory) and destructures what it needs from the shared `ctx`, so the hook bodies read as they did in the original single script.

| Family | Module | Events emitted |
|---|---|---|
| Shared state and hooking helpers | `registry.js` | none |
| Browser script delivery and probe polling | `browser_delivery.js` | `js.probe`, `js.probe.error` |
| WebView lifecycle and navigation | `webview_lifecycle.js` | `webview.created`, `webview.added`, `url.loaded` |
| WebSettings setters | `webview_settings.js` | `webview.settings.changed` |
| Client callbacks | `webview_clients.js` | `webview.client.set`, `webview.chrome_client.set`, `webview.page.loaded`, `url.loaded` |
| JavaScript bridge | `javascript_bridge.js` | `bridge.added`, `bridge.method.added`, `bridge.method.called`, `js.probe.error` |
| JavaScript evaluation | `javascript_evaluation.js` | `js.evaluated` |
| Permissions | `permissions.js` | `permission.requested`, `permission.grant.called`, `permission.deny.called` |
| Environment | `environment.js` | none (rewrites `System.getenv("URL")` for the demo app) |
| Entry point | `main.js` | none (installs everything, polls and flushes) |

## The `ctx` object

`main.js` builds it inside `Java.perform`, in this order:

1. The Java class handles: `WebView`, `WebSettings`, `PermissionRequest`, `ValueCallback`, `StringClass`, `Modifier`, `JavascriptInterface` and others, plus `log` from `core/agent/emitter.js`.
2. `createRegistry()`: the WebView maps and helpers (`getWebViewState`, `updateWebViewUrl`, `keyFor`, `stringValue`, `hookMethod`, …).
3. `createDelivery(ctx)`: `inject`, `injectBridgeTaintWrappers`, `evaluateOnWebView`, `ProbeCallback`, `pollAll`.
4. `createClientHookers(ctx)`: `hookWebViewClientClass`, `hookWebChromeClientClass`.

## Install order

The hooks are installed in the same order as the original script:

1. base client classes
2. constructors and `getSettings`
3. client setters
4. load methods
5. `evaluateJavascript`
6. bridge
7. settings
8. permission grant and deny
9. the poll/flush timer

`environment.js` comes **after** `main.js` in the bundle and uses its own `Java.perform`. The original agent loaded `getenv.js` as a second script, and keeping a separate callback means a failure in the WebView hooks still can't stop the `getenv` shim from being installed.

## Changing a hook family

- Edit only that family's module. Use `log(EVENT_TYPE.X, {...})` with the vocabulary in `core/events/event_types.json`.
- Code that runs inside the page belongs in `browser/`, never here.
- A new module also needs an entry in `core/agent/manifest.json`, before `native/main.js`.
- Check your change with `python3 -m unittest tests.test_native_parity tests.test_layering_native tests.test_agent_bundle`. `test_native_parity` drives every hook family against a mocked Java runtime and compares the events with the original agent. A **deliberate** behavior change will make it fail; that's expected.
