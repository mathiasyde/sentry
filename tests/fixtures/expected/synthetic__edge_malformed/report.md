# Sentry WebView Security Report

## Summary

- Risk score: 20/100
- Events analyzed: 3
- Findings: 1
- WebViews observed: 2
- Skipped non-event lines: 6

## Severity Counts

- Critical: 0
- High: 1
- Medium: 0
- Low: 0
- Info: 0

## Findings

### 1. [HIGH] Cleartext HTTP content loaded in WebView

- Rule: `WV-CLEARTEXT-URL`
- Description: The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.
- Recommendation: Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:01.000Z", "url": "http://x.example/", "webViewId": "android.webkit.WebView:111"}`


## WebView Inventory

### WebView android.webkit.WebView:111

- URLs observed: 1
- Settings observed: 0
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 0
- Recent URLs:
  - `http://x.example/`

### WebView unknown

- URLs observed: 0
- Settings observed: 0
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 0


## Sensitive Data Flows

No sensitive bridge-return values were observed reaching JavaScript sinks.

## Origin To Bridge Map

### WebView android.webkit.WebView:111

No JavaScript bridge origins were observed for this WebView.

### WebView unknown

No JavaScript bridge origins were observed for this WebView.
