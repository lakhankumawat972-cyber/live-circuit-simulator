import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSyncer } from '../src/syncer.js';
import { controllableFetch, fakeClock, flush, okBody } from './helpers.js';

function setup(options = {}) {
  const clock = fakeClock();
  const net = controllableFetch(options);
  const updates = [];
  const syncer = createSyncer({
    endpoint: '/api/simulate',
    fetchFn: net.fetchFn,
    onUpdate: (u) => updates.push(u),
    debounceMs: 250,
    requestTimeoutMs: 15_000,
    retryDelays: [1000, 2000, 4000],
    setTimer: clock.setTimer,
    clearTimer: clock.clearTimer,
  });
  const phases = () => updates.map((u) => u.phase);
  const last = (phase) => [...updates].reverse().find((u) => u.phase === phase);
  return { clock, net, updates, syncer, phases, last };
}

const graph = (value) => ({ nodes: [{ id: 'n', type: 'number', data: { value } }], edges: [] });

test('typing 1, 10, 100 quickly sends one request with the last value', async () => {
  const { clock, net, syncer } = setup();
  syncer.push(graph('1'));
  await clock.advance(100);
  syncer.push(graph('10'));
  await clock.advance(100);
  syncer.push(graph('100'));
  await clock.advance(249);
  assert.equal(net.calls.length, 0);
  await clock.advance(1);
  assert.equal(net.calls.length, 1);
  assert.equal(net.calls[0].body.nodes[0].data.value, '100');
  assert.equal(net.calls[0].body.version, 3);
});

test('a newer edit aborts the request still in flight: requests never pile up', async () => {
  const { clock, net, syncer } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  assert.equal(net.calls.length, 1);
  syncer.push(graph('10'));
  assert.equal(net.calls[0].signal.aborted, true);
  await clock.advance(250);
  assert.equal(net.calls.length, 2);
  assert.equal(net.calls[1].signal.aborted, false);
});

test('an old answer that arrives late (even if abort was ignored) never reaches the canvas', async () => {
  const { clock, net, syncer, updates, last } = setup({ honourAbort: false });
  syncer.push(graph('1'));
  await clock.advance(250);
  syncer.push(graph('10'));
  await clock.advance(250);
  assert.equal(net.calls.length, 2);
  net.calls[1].respond(200, okBody(2, { nodes: { n: { status: 'ok', value: 10 } } }));
  await flush();
  net.calls[0].respond(200, okBody(1, { nodes: { n: { status: 'ok', value: 1 } } })); // out of order
  await flush();
  const oks = updates.filter((u) => u.phase === 'ok');
  assert.equal(oks.length, 1);
  assert.equal(oks[0].result.nodes.n.value, 10);
  assert.equal(last('ok').version, 2);
});

test('an answer for another version is ignored even if nothing newer was sent', async () => {
  const { clock, net, syncer, phases } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  net.calls[0].respond(200, okBody(99));
  await flush();
  assert.deepEqual(phases(), ['pending']);
});

test('API unreachable: shows offline, retries with backoff, recovers on its own', async () => {
  const { clock, net, syncer, phases, last } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  net.calls[0].fail();
  await flush();
  assert.equal(last('offline').retryInMs, 1000);
  await clock.advance(1000);
  assert.equal(net.calls.length, 2);
  net.calls[1].fail();
  await flush();
  assert.equal(last('offline').retryInMs, 2000);
  await clock.advance(2000);
  net.calls[2].respond(200, okBody(1));
  await flush();
  assert.deepEqual(phases(), ['pending', 'offline', 'offline', 'ok']);
  assert.equal(clock.pending(), 0);
});

test('simulator timeout or crash is a "degraded" state and is retried', async () => {
  const { clock, net, syncer, last } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  net.calls[0].respond(504, okBody(1, { engine: { state: 'timeout', message: 'ngspice did not finish' } }));
  await flush();
  assert.equal(last('degraded').message, 'ngspice did not finish');
  assert.equal(last('degraded').retryInMs, 1000);
  await clock.advance(1000);
  net.calls[1].respond(200, okBody(1));
  await flush();
  assert.ok(last('ok'));
});

test('a request that never answers is given up on and retried', async () => {
  const { clock, net, syncer, last } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  await clock.advance(15_000);
  assert.equal(net.calls[0].signal.aborted, true);
  assert.equal(last('offline').message, 'The API did not answer in time');
});

test('a new edit cancels a scheduled retry of the old graph', async () => {
  const { clock, net, syncer } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  net.calls[0].fail();
  await flush();
  syncer.push(graph('2'));
  await clock.advance(250);
  assert.equal(net.calls.length, 2);
  assert.equal(net.calls[1].body.nodes[0].data.value, '2');
  await clock.advance(5000);
  assert.equal(net.calls.length, 2);
});

test('a rejected graph (4xx) is shown as an error and not retried', async () => {
  const { clock, net, syncer, last } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  net.calls[0].respond(400, { error: 'Graph is too large', version: 1 });
  await flush();
  assert.equal(last('error').message, 'Graph is too large');
  await clock.advance(30_000);
  assert.equal(net.calls.length, 1);
});

test('destroy stops everything', async () => {
  const { clock, net, syncer, updates } = setup();
  syncer.push(graph('1'));
  await clock.advance(250);
  syncer.destroy();
  assert.equal(net.calls[0].signal.aborted, true);
  const before = updates.length;
  syncer.push(graph('2'));
  await clock.advance(1000);
  assert.equal(updates.length, before);
});
