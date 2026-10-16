# Sentry WebView Security Report

## Summary

- Risk score: 40/100
- Events analyzed: 9
- Findings: 6
- WebViews observed: 1
- Skipped non-event lines: 0

## Severity Counts

- Critical: 0
- High: 0
- Medium: 4
- Low: 0
- Info: 2

## Findings

### 1. [MEDIUM] WebView JavaScript contacted a cleartext URL

- Rule: `WV-JS-CLEARTEXT-NETWORK`
- Description: JavaScript running inside the WebView made or prepared a cleartext HTTP request.
- Recommendation: Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.
- Evidence:
  - `{"api": "fetch", "href": "https://app.example/", "timestamp": "2026-01-01T00:00:03.000Z", "url": "http://api.example/data", "webViewId": "android.webkit.WebView:222"}`

### 2. [MEDIUM] WebView JavaScript contacted a cleartext URL

- Rule: `WV-JS-CLEARTEXT-NETWORK`
- Description: JavaScript running inside the WebView made or prepared a cleartext HTTP request.
- Recommendation: Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.
- Evidence:
  - `{"api": "XMLHttpRequest.open", "href": "https://app.example/", "timestamp": "2026-01-01T00:00:05.000Z", "url": "http://api.example/xhr", "webViewId": "android.webkit.WebView:222"}`

### 3. [MEDIUM] WebView page executed JavaScript eval

- Rule: `WV-JS-EVAL`
- Description: JavaScript running inside the WebView called eval, which increases XSS and injection impact.
- Recommendation: Avoid eval and use safer parsing or dispatch mechanisms.
- Evidence:
  - `{"arguments": ["1+1"], "href": "https://app.example/", "timestamp": "2026-01-01T00:00:02.000Z", "webViewId": "android.webkit.WebView:222"}`

### 4. [MEDIUM] Native code evaluated JavaScript in WebView

- Rule: `WV-JS-EVALUATED`
- Description: The app called evaluateJavascript. If script contents include attacker-controlled data, this can become JavaScript injection.
- Recommendation: Avoid string-built JavaScript. Use structured message passing and encode any values inserted into JavaScript code.
- Evidence:
  - `{"pageUrl": "https://app.example/", "script": "window.init()", "timestamp": "2026-01-01T00:00:00.000Z", "webViewId": "android.webkit.WebView:222"}`
  - `{"pageUrl": "https://app.example/", "script": "window.init()", "timestamp": "2026-01-01T00:00:01.000Z", "webViewId": "android.webkit.WebView:222"}`

### 5. [INFO] JavaScript probe reported an error

- Rule: `WV-PROBE-ERROR`
- Description: The injected JavaScript probe could not run or parse its result for at least one WebView state.
- Recommendation: Review whether the page navigated, blocked script execution, or removed probe state.
- Evidence:
  - `{"error": "Error: blocked", "href": null, "timestamp": "2026-01-01T00:00:07.000Z", "webViewId": "android.webkit.WebView:222"}`

### 6. [INFO] JavaScript probe reported an error

- Rule: `WV-PROBE-ERROR`
- Description: The injected JavaScript probe could not run or parse its result for at least one WebView state.
- Recommendation: Review whether the page navigated, blocked script execution, or removed probe state.
- Evidence:
  - `{"error": "failed to parse probe result", "href": "https://app.example/", "timestamp": "2026-01-01T00:00:08.000Z", "webViewId": "android.webkit.WebView:222"}`


## WebView Inventory

### WebView android.webkit.WebView:222

- URLs observed: 0
- Settings observed: 0
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 5


## Sensitive Data Flows

No sensitive bridge-return values were observed reaching JavaScript sinks.

## Origin To Bridge Map

### WebView android.webkit.WebView:222

No JavaScript bridge origins were observed for this WebView.
