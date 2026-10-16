// core/agent: safe serializer applied to every event before it is printed.
// Safe serializer that handles circular refs and Frida Java proxies.
function sanitize(value, seen = new Set()) {
  if (value === null || value === undefined) return null;
  const t = typeof value;
  if (t === "string" || t === "number" || t === "boolean") return value;
  if (t === "function") return `[Function: ${value.name || "anonymous"}]`;
  if (seen.has(value)) return "[Circular]";
  if (Array.isArray(value)) {
    seen.add(value);
    const arr = value.map((v) => sanitize(v, seen));
    seen.delete(value);
    return arr;
  }
  if (t === "object") {
    if (value.$className) {
      try {
        return value.toString();
      } catch (e) {
        return `[Java object ${value.$className}]`;
      }
    }
    seen.add(value);
    const out = {};
    for (const k in value) {
      try {
        out[k] = sanitize(value[k], seen);
      } catch (e) {
        out[k] = "[Unserializable]";
      }
    }
    seen.delete(value);
    return out;
  }
  return String(value);
}
