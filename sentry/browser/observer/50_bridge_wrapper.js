// browser: wraps sensitive JavaScript bridge methods so their return values become taint sources.
  state.wrapBridgeMethod = function(interfaceName, methodName, source) {
    const key = interfaceName + "." + methodName;
    if (state.bridgeWrappers[key]) { return true; }

    const bridge = window[interfaceName];
    if (!bridge || typeof bridge[methodName] !== "function") {
      return false;
    }

    const original = bridge[methodName];
    const wrapped = function() {
      const args = Array.prototype.slice.call(arguments).map(function (arg) {
        return copyArg(arg, 0);
      });
      const result = original.apply(this, arguments);
      const taint = rememberTaint(result, source);
      report({
        name: "bridge.method.return.tainted",
        arguments: args,
        taints: taint ? [{
          argumentIndex: -1,
          taintId: taint.id,
          source: taint.source,
          valuePreview: taint.valuePreview,
        }] : [],
        bridge: {
          interfaceName: interfaceName,
          methodName: methodName,
        },
      });
      return result;
    };

    Object.defineProperty(wrapped, "__sentryWrapped", {
      value: true,
      configurable: false,
      enumerable: false,
      writable: false,
    });

    try {
      bridge[methodName] = wrapped;
      state.bridgeWrappers[key] = true;
      return true;
    } catch (e) {
      report({
        name: "bridge.method.wrap.failed",
        arguments: [interfaceName, methodName, String(e)],
      });
      return false;
    }
  };

  return true;
