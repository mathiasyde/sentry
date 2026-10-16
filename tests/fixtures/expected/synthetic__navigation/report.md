# Sentry WebView Security Report

## Summary

- Risk score: 70/100
- Events analyzed: 13
- Findings: 5
- WebViews observed: 2
- Skipped non-event lines: 0

## Severity Counts

- Critical: 0
- High: 2
- Medium: 3
- Low: 0
- Info: 0

## Findings

### 1. [HIGH] Cleartext HTTP content loaded in WebView

- Rule: `WV-CLEARTEXT-URL`
- Description: The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.
- Recommendation: Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:03.000Z", "url": "http://insecure.example/index.html", "webViewId": "android.webkit.WebView:111"}`
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:04.000Z", "url": "http://insecure.example/index.html", "webViewId": "android.webkit.WebView:111"}`

### 2. [HIGH] file:// content loaded in WebView

- Rule: `WV-FILE-URL-LOADED`
- Description: The WebView loaded local file content. file:// pages are risky when file access or JavaScript bridges are enabled.
- Recommendation: Avoid file:// content for untrusted pages. Prefer WebViewAssetLoader or a tightly controlled HTTPS origin.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:05.000Z", "url": "file:///android_asset/index.html", "webViewId": "android.webkit.WebView:111"}`

### 3. [MEDIUM] Inline HTML content loaded in WebView

- Rule: `WV-INLINE-CONTENT`
- Description: The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.
- Recommendation: Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.
- Evidence:
  - `{"source": "loadData", "timestamp": "2026-01-01T00:00:06.000Z", "url": null, "webViewId": "android.webkit.WebView:111"}`

### 4. [MEDIUM] Inline HTML content loaded in WebView

- Rule: `WV-INLINE-CONTENT`
- Description: The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.
- Recommendation: Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.
- Evidence:
  - `{"source": "loadDataWithBaseURL", "timestamp": "2026-01-01T00:00:07.000Z", "url": "https://app.example/", "webViewId": "android.webkit.WebView:111"}`

### 5. [MEDIUM] Inline HTML content loaded in WebView

- Rule: `WV-INLINE-CONTENT`
- Description: The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.
- Recommendation: Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:08.000Z", "url": "data:text/html,<b>hi</b>", "webViewId": "android.webkit.WebView:111"}`


## WebView Inventory

### WebView android.webkit.WebView:111

- URLs observed: 7
- Settings observed: 0
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 0
- Recent URLs:
  - `file:///android_asset/index.html`
  - `https://app.example/`
  - `data:text/html,<b>hi</b>`
  - `https://app.example/home`
  - `https://app.example/post`

### WebView unknown

- URLs observed: 1
- Settings observed: 0
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 0
- Recent URLs:
  - `about:blank`


## Sensitive Data Flows

No sensitive bridge-return values were observed reaching JavaScript sinks.

## Origin To Bridge Map

### WebView android.webkit.WebView:111

No JavaScript bridge origins were observed for this WebView.

### WebView unknown

No JavaScript bridge origins were observed for this WebView.
