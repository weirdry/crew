// Observe real tree requests, or control only that response for update scenarios.
// Never record request headers, credentials or response bodies.
const fs = require('node:fs');
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, options) => {
  const url = new URL(typeof input === 'string' ? input : input.url || input.href);
  if (url.origin !== 'https://api.github.com' || !url.pathname.includes('/git/trees/')) {
    return originalFetch(input, options);
  }
  const mode = process.env.CREW_TEST_TREE_MODE;
  const event = { mode, url: url.href };
  try {
    let response;
    if (mode === 'live') {
      response = await originalFetch(input, options);
    } else {
      if (url.href !== process.env.CREW_TEST_TREE_URL) {
        throw new Error('Unexpected tree request in controlled scenario');
      }
      if (mode === 'tree') {
        response = new Response(fs.readFileSync(process.env.CREW_TEST_TREE_FIXTURE), {
          status: 200, headers: { 'content-type': 'application/json' },
        });
      } else if (mode === 'unavailable') {
        response = new Response('Synthetic API unavailability', { status: 503 });
      } else {
        throw new Error('Unknown tree response mode');
      }
    }
    event.status = response.status;
    for (const name of ['x-ratelimit-remaining', 'x-ratelimit-reset', 'retry-after']) {
      const value = response.headers.get(name);
      if (value !== null) event[name] = value;
    }
    return response;
  } catch (error) {
    event.error = error.name;
    event.code = error.cause?.code || error.code || null;
    throw error;
  } finally {
    fs.appendFileSync(process.env.CREW_TEST_HTTP_LOG, JSON.stringify(event) + '\n');
  }
};
