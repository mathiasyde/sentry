# Sentry WebView Security Report

## Summary

- Risk score: 100/100
- Events analyzed: 13
- Findings: 9
- WebViews observed: 2
- Skipped non-event lines: 0

## Severity Counts

- Critical: 1
- High: 2
- Medium: 3
- Low: 3
- Info: 0

## Findings

### 1. [CRITICAL] File URLs can access arbitrary origins

- Rule: `WV-UNIVERSAL-FILE-ACCESS`
- Description: A file:// page can make network requests to arbitrary origins. This is a high-impact WebView misconfiguration.
- Recommendation: Keep allowUniversalAccessFromFileURLs disabled and serve local content from a constrained WebViewAssetLoader origin when possible.
- Evidence:
  - `{"setting": "setAllowUniversalAccessFromFileURLs", "timestamp": "2026-01-01T00:00:05.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 2. [HIGH] File URLs can access other file URLs

- Rule: `WV-FILE-FROM-FILE`
- Description: A page loaded from file:// can read other file:// resources, which can expose local app or device files.
- Recommendation: Keep allowFileAccessFromFileURLs disabled and avoid loading untrusted file:// pages.
- Evidence:
  - `{"setting": "setAllowFileAccessFromFileURLs", "timestamp": "2026-01-01T00:00:04.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 3. [HIGH] Mixed content is always allowed

- Rule: `WV-MIXED-CONTENT`
- Description: The WebView allows HTTPS pages to load cleartext HTTP subresources, weakening transport security.
- Recommendation: Use MIXED_CONTENT_NEVER_ALLOW unless a documented legacy compatibility case exists.
- Evidence:
  - `{"setting": "setMixedContentMode", "timestamp": "2026-01-01T00:00:09.000Z", "value": 0, "webViewId": "android.webkit.WebView:111"}`

### 4. [MEDIUM] File access is enabled

- Rule: `WV-FILE-ACCESS`
- Description: The WebView can access local files. Combined with file URLs, content injection, or permissive bridge methods, this can expose app-private data.
- Recommendation: Disable file access unless the app has a specific local-content use case.
- Evidence:
  - `{"setting": "setAllowFileAccess", "timestamp": "2026-01-01T00:00:02.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`
  - `{"setting": "setAllowFileAccess", "timestamp": "2026-01-01T00:00:11.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 5. [MEDIUM] JavaScript execution is enabled

- Rule: `WV-JS-ENABLED`
- Description: JavaScript is enabled in a WebView. This is expected for hybrid apps, but it increases the impact of untrusted content, XSS, and exposed JavaScript bridges.
- Recommendation: Only enable JavaScript for trusted content and pair it with strict origin checks before exposing native bridges.
- Evidence:
  - `{"setting": "setJavaScriptEnabled", "timestamp": "2026-01-01T00:00:01.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 6. [MEDIUM] Safe Browsing is disabled

- Rule: `WV-SAFE-BROWSING-DISABLED`
- Description: WebView Safe Browsing was disabled, reducing protection against known malicious URLs.
- Recommendation: Leave Safe Browsing enabled unless there is a documented compatibility reason.
- Evidence:
  - `{"setting": "setSafeBrowsingEnabled", "timestamp": "2026-01-01T00:00:06.000Z", "value": false, "webViewId": "android.webkit.WebView:111"}`

### 7. [LOW] Content provider access is enabled

- Rule: `WV-CONTENT-ACCESS`
- Description: The WebView can load content:// resources. This can become risky when untrusted content can influence loaded URLs.
- Recommendation: Disable content access unless required and validate all content:// URLs before loading them.
- Evidence:
  - `{"setting": "setAllowContentAccess", "timestamp": "2026-01-01T00:00:03.000Z", "value": "true", "webViewId": "android.webkit.WebView:111"}`

### 8. [LOW] Geolocation is enabled

- Rule: `WV-GEOLOCATION-ENABLED`
- Description: Geolocation support is enabled in WebView content.
- Recommendation: Only allow geolocation for trusted origins and ensure prompts are not auto-approved.
- Evidence:
  - `{"setting": "setGeolocationEnabled", "timestamp": "2026-01-01T00:00:07.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 9. [LOW] JavaScript can open windows automatically

- Rule: `WV-JS-POPUPS`
- Description: JavaScript is allowed to open windows without user gestures, which can enable unwanted navigation flows.
- Recommendation: Disable automatic window opening unless required by trusted content.
- Evidence:
  - `{"setting": "setJavaScriptCanOpenWindowsAutomatically", "timestamp": "2026-01-01T00:00:08.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`


## WebView Inventory

### WebView android.webkit.WebView:111

- URLs observed: 0
- Settings observed: 10
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 0

### WebView unknown

- URLs observed: 0
- Settings observed: 1
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
