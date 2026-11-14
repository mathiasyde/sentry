// browser: wraps Storage setItem/getItem so taints survive a round trip through web storage.
  if (window.Storage && Storage.prototype) {
    const originalSetItem = Storage.prototype.setItem;
    const originalGetItem = Storage.prototype.getItem;

    if (typeof originalSetItem === "function" && !originalSetItem.__sentryWrapped) {
      Storage.prototype.setItem = function(key, value) {
        const taints = taintsForArgs(arguments);
        if (taints.length > 0) {
          state.taintedStorage[String(key)] = taints[0];
        }
        report({
          name: "localStorage.setItem",
          arguments: [copyArg(key, 0), copyArg(value, 0)],
          taints: taints,
        });
        return originalSetItem.apply(this, arguments);
      };
      Object.defineProperty(Storage.prototype.setItem, "__sentryWrapped", {
        value: true,
        configurable: false,
        enumerable: false,
        writable: false,
      });
    }

    if (typeof originalGetItem === "function" && !originalGetItem.__sentryWrapped) {
      Storage.prototype.getItem = function(key) {
        const result = originalGetItem.apply(this, arguments);
        const storedTaint = state.taintedStorage[String(key)];
        if (storedTaint && result !== null && result !== undefined) {
          rememberTaint(result, storedTaint.source);
        }
        report({
          name: "localStorage.getItem",
          arguments: [copyArg(key, 0)],
          taints: storedTaint ? [storedTaint] : [],
        });
        return result;
      };
      Object.defineProperty(Storage.prototype.getItem, "__sentryWrapped", {
        value: true,
        configurable: false,
        enumerable: false,
        writable: false,
      });
    }
  }
