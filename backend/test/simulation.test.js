import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSimulationClient } from '../src/simulation.js';

const payload = { version: 3, nodes: [], edges: [] };
const json = (status, body) => ({ ok: status < 300, status, json: async () => body });
const client = (fetchFn, timeoutMs = 1000) => createSimulationClient({ baseUrl: 'http://sim', fetchFn, timeoutMs });

// a fetch that never answers but honours abort, like the real one
const hanging = (_url, { signal }) =>
  new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));

test('passes a good answer through and posts to /simulate', async () => {
  let seen;
  const out = await client(async (url, init) => {
    seen = { url, body: JSON.parse(init.body) };
    return json(200, { version: 3, nodes: { a: { status: 'ok', value: 1 } }, engine: { state: 'ok' } });
  }).simulate(payload);
  assert.equal(out.status, 200);
  assert.equal(out.body.nodes.a.value, 1);
  assert.equal(seen.url, 'http://sim/simulate');
  assert.equal(seen.body.version, 3);
});

test('service down -> 503 with engine.state "unavailable" (never throws)', async () => {
  const out = await client(async () => {
    throw new TypeError('fetch failed');
  }).simulate(payload);
  assert.equal(out.status, 503);
  assert.equal(out.body.engine.state, 'unavailable');
  assert.equal(out.body.version, 3);
});

test('service hangs -> 504 with engine.state "timeout"', async () => {
  const out = await client(hanging, 30).simulate(payload);
  assert.equal(out.status, 504);
  assert.equal(out.body.engine.state, 'timeout');
});

test('browser abandons the request -> upstream call is cancelled, nothing is answered', async () => {
  const abort = new AbortController();
  const pending = client(hanging, 5000).simulate(payload, { signal: abort.signal });
  abort.abort();
  assert.deepEqual(await pending, { aborted: true });
});

test('service errors and garbage become engine errors', async () => {
  const crashed = await client(async () => json(500, { detail: 'boom' })).simulate(payload);
  assert.equal(crashed.status, 502);
  assert.equal(crashed.body.engine.state, 'error');
  const garbage = await client(async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError('x'); } })).simulate(payload);
  assert.equal(garbage.body.engine.state, 'error');
});

test('a graph the service refuses (422) is reported as a client error', async () => {
  const out = await client(async () => json(422, { detail: 'Duplicate node id' })).simulate(payload);
  assert.equal(out.status, 422);
  assert.match(out.body.error, /Duplicate/);
});
