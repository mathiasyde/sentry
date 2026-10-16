// browser: fingerprints values returned by sensitive bridge methods and finds them again in later calls.
  function fingerprint(value) {
    if (value === null || value === undefined) { return null; }

    try {
      if (typeof value === "string") {
        return value.length ? value.slice(0, 512) : null;
      }
      if (typeof value === "number" || typeof value === "boolean") {
        return String(value);
      }
      const json = JSON.stringify(copyArg(value, 0));
      return json && json !== "null" ? json.slice(0, 512) : null;
    } catch (e) {
      return String(value).slice(0, 512);
    }
  }

  function rememberTaint(value, source) {
    const fp = fingerprint(value);
    if (!fp) { return null; }

    const taint = {
      id: "taint-" + Date.now() + "-" + state.taints.length,
      source: source,
      valuePreview: fp.slice(0, 120),
    };

    state.taints.push(taint);
    state.taintByValue[fp] = taint;

    if (state.taints.length > 200) {
      const removed = state.taints.splice(0, state.taints.length - 200);
      removed.forEach(function (item) {
        Object.keys(state.taintByValue).forEach(function (key) {
          if (state.taintByValue[key] === item) {
            delete state.taintByValue[key];
          }
        });
      });
    }

    return taint;
  }

  function findTaint(value) {
    const fp = fingerprint(value);
    if (fp && state.taintByValue[fp]) {
      return state.taintByValue[fp];
    }

    if (typeof value === "string") {
      for (const key in state.taintByValue) {
        if (key.length >= 8 && value.indexOf(key) !== -1) {
          return state.taintByValue[key];
        }
      }
    }

    if (Array.isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        const taint = findTaint(value[i]);
        if (taint) { return taint; }
      }
    }

    if (value && typeof value === "object") {
      const keys = Object.keys(value).slice(0, 20);
      for (let i = 0; i < keys.length; i++) {
        let taint = null;
        try {
          taint = findTaint(value[keys[i]]);
        } catch (e) {
          taint = null;
        }
        if (taint) { return taint; }
      }
    }

    return null;
  }

  function taintsForArgs(args) {
    const taints = [];
    Array.prototype.slice.call(args).forEach(function (arg, index) {
      const taint = findTaint(arg);
      if (taint) {
        taints.push({
          argumentIndex: index,
          taintId: taint.id,
          source: taint.source,
          valuePreview: taint.valuePreview,
        });
      }
    });
    return taints;
  }
