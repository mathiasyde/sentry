// core/agent: event queue shared by all native hooks; flushed to stdout once per poll tick.
const messages = [];

function log(type, data, timestamp = new Date().toISOString()) {
  messages.push({ type: type, timestamp: timestamp, data: data });
}

function flush() {
  messages.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
  messages.forEach((message) => {
    console.log(JSON.stringify(sanitize(message)));
  });

  messages.length = 0;
}
