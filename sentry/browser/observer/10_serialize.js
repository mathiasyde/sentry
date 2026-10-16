// browser: copies call arguments safely and buffers page events (at most 500).
  function copyArg(arg, depth) {
    if (depth > 2) { return "[MaxDepth]"; }
    if (arg === null || arg === undefined) { return null; }
    const t = typeof arg;
    if (t === "string" || t === "number" || t === "boolean") {
      return arg;
    }
    if (t === "function") {
      return "[Function: " + (arg.name || "anonymous") + "]";
    }
    if (Array.isArray(arg)) {
      return arg.slice(0, 20).map(function (item) {
        return copyArg(item, depth + 1);
      });
    }
    if (t === "object") {
      const out = {};
      Object.keys(arg).slice(0, 20).forEach(function (key) {
        try {
          out[key] = copyArg(arg[key], depth + 1);
        } catch (e) {
          out[key] = "[Unserializable]";
        }
      });
      return out;
    }
    return String(arg);
  }

  function report(event) {
    state.events.push({
      timestamp: new Date().toISOString(),
      name: event.name,
      arguments: event.arguments || [],
    });

    if (state.events.length > 500) {
      state.events.splice(0, state.events.length - 500);
    }
  }
