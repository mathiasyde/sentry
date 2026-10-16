# Sentry WebView Security Report

## Summary

- Risk score: 53/100
- Events analyzed: 6
- Findings: 5
- WebViews observed: 0
- Skipped non-event lines: 0

## Severity Counts

- Critical: 0
- High: 1
- Medium: 3
- Low: 1
- Info: 0

## Findings

### 1. [HIGH] WebView permission was granted to web content

- Rule: `WV-WEB-PERMISSION-GRANTED`
- Description: A WebView permission request was granted. Camera, microphone, and geolocation grants can expose sensitive user data to web content.
- Recommendation: Only grant permissions to a small allowlist of HTTPS origins and never grant all requested resources blindly.
- Evidence:
  - `{"origin": "http://remote.example/", "resources": ["android.webkit.resource.AUDIO_CAPTURE"], "timestamp": "2026-01-01T00:00:03.000Z"}`

### 2. [MEDIUM] WebView permission was granted to web content

- Rule: `WV-WEB-PERMISSION-GRANTED`
- Description: A WebView permission request was granted. Camera, microphone, and geolocation grants can expose sensitive user data to web content.
- Recommendation: Only grant permissions to a small allowlist of HTTPS origins and never grant all requested resources blindly.
- Evidence:
  - `{"origin": "https://app.example/", "resources": ["android.webkit.resource.VIDEO_CAPTURE"], "timestamp": "2026-01-01T00:00:04.000Z"}`

### 3. [MEDIUM] WebView content requested a browser permission

- Rule: `WV-WEB-PERMISSION-REQUEST`
- Description: Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.
- Recommendation: Grant WebView permissions only after validating the request origin and the exact requested resources.
- Evidence:
  - `{"origin": "https://app.example/", "resources": ["android.webkit.resource.VIDEO_CAPTURE"], "timestamp": "2026-01-01T00:00:00.000Z", "type": null}`

### 4. [MEDIUM] WebView content requested a browser permission

- Rule: `WV-WEB-PERMISSION-REQUEST`
- Description: Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.
- Recommendation: Grant WebView permissions only after validating the request origin and the exact requested resources.
- Evidence:
  - `{"origin": "http://remote.example/", "resources": null, "timestamp": "2026-01-01T00:00:01.000Z", "type": "geolocation"}`

### 5. [LOW] WebView content requested a browser permission

- Rule: `WV-WEB-PERMISSION-REQUEST`
- Description: Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.
- Recommendation: Grant WebView permissions only after validating the request origin and the exact requested resources.
- Evidence:
  - `{"origin": null, "resources": [], "timestamp": "2026-01-01T00:00:02.000Z", "type": null}`


## WebView Inventory

No WebView activity was observed.

## Sensitive Data Flows

No sensitive bridge-return values were observed reaching JavaScript sinks.

## Origin To Bridge Map

No JavaScript bridge origins were observed.
