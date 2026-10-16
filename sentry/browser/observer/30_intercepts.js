// browser: wraps page APIs (fetch, eval, window.open, postMessage, sendBeacon, location, XMLHttpRequest).
  function intercept(owner, property, name) {
    try {
      const original = owner && owner[property];
      if (typeof original !== "function" || original.__sentryWrapped) {
        return;
      }

      const wrapped = function() {
        const rawArgs = Array.prototype.slice.call(arguments);
        const args = rawArgs.map(function (arg) {
          return copyArg(arg, 0);
        });
        const taints = taintsForArgs(rawArgs);
        report({ name: name, arguments: args, taints: taints });
        return original.apply(this, arguments);
      };

      Object.defineProperty(wrapped, "__sentryWrapped", {
        value: true,
        configurable: false,
        enumerable: false,
        writable: false,
      });

      owner[property] = wrapped;
    } catch (e) {
      report({ name: "sentry.intercept.failed", arguments: [name, String(e)] });
    }
  }

  intercept(window, "fetch", "fetch");
  intercept(window, "eval", "eval");
  intercept(window, "open", "window.open");
  intercept(window, "postMessage", "window.postMessage");

  if (window.navigator) {
    intercept(window.navigator, "sendBeacon", "navigator.sendBeacon");
  }

  if (window.Location && Location.prototype) {
    intercept(Location.prototype, "assign", "location.assign");
    intercept(Location.prototype, "replace", "location.replace");
  }

  if (window.XMLHttpRequest && XMLHttpRequest.prototype) {
    intercept(XMLHttpRequest.prototype, "send", "XMLHttpRequest.send");
    intercept(XMLHttpRequest.prototype, "open", "XMLHttpRequest.open");
  }
