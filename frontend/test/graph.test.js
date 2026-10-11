import assert from 'node:assert/strict';
import { test } from 'node:test';
import { canConnect, formatValue, fromStored, signature, toPayload, toStored } from '../src/graph.js';

const n = (id, type, extra = {}) => ({ id, type, position: { x: 10, y: 20 }, data: {}, ...extra });
const nodes = [n('a', 'number'), n('b', 'number'), n('add', 'add'), n('out', 'display'), n('f', 'formula')];
const wire = (source, target, targetHandle, sourceHandle = 'out') => ({ id: `${source}-${target}-${targetHandle}`, source, target, sourceHandle, targetHandle });

test('allows output -> input', () => {
  assert.equal(canConnect(wire('a', 'add', 'a'), nodes, []), true);
  assert.equal(canConnect(wire('add', 'out', 'x'), nodes, []), true);
});

test('one output may feed many inputs, including both inputs of one node', () => {
  const edges = [wire('a', 'add', 'a')];
  assert.equal(canConnect(wire('a', 'add', 'b'), nodes, edges), true);
  assert.equal(canConnect(wire('a', 'f', 'a'), nodes, edges), true);
});

test('blocks a second wire into an occupied input', () => {
  assert.equal(canConnect(wire('b', 'add', 'a'), nodes, [wire('a', 'add', 'a')]), false);
});

test('blocks a node wired to itself', () => {
  assert.equal(canConnect(wire('add', 'add', 'a'), nodes, []), false);
});

test('blocks input -> input and output -> output', () => {
  assert.equal(canConnect({ source: 'add', target: 'out', sourceHandle: 'a', targetHandle: 'x' }, nodes, []), false);
  assert.equal(canConnect({ source: 'a', target: 'b', sourceHandle: 'out', targetHandle: 'out' }, nodes, []), false);
});

test('blocks wires out of a Display and into a Number', () => {
  assert.equal(canConnect(wire('out', 'add', 'a'), nodes, []), false);
  assert.equal(canConnect(wire('add', 'a', 'x'), nodes, []), false);
});

test('blocks unknown nodes and handles', () => {
  assert.equal(canConnect(wire('ghost', 'add', 'a'), nodes, []), false);
  assert.equal(canConnect(wire('a', 'add', 'zzz'), nodes, []), false);
});

test('a loop is allowed to be drawn (the backend flags it on the nodes)', () => {
  const two = [n('p', 'add'), n('q', 'multiply')];
  assert.equal(canConnect(wire('q', 'p', 'a'), two, [wire('p', 'q', 'a')]), true);
});

test('moving or selecting nodes does not change the signature; edits and rewiring do', () => {
  const base = signature(toPayload([n('a', 'number', { data: { value: '1' } })], []));
  const moved = signature(toPayload([n('a', 'number', { position: { x: 99, y: 99 }, selected: true, data: { value: '1' } })], []));
  const edited = signature(toPayload([n('a', 'number', { data: { value: '10' } })], []));
  assert.equal(base, moved);
  assert.notEqual(base, edited);
  const g = [n('a', 'number'), n('d', 'display')];
  assert.notEqual(signature(toPayload(g, [])), signature(toPayload(g, [wire('a', 'd', 'x')])));
});

test('node order does not change the signature', () => {
  const x = signature(toPayload([n('a', 'number'), n('b', 'number')], []));
  const y = signature(toPayload([n('b', 'number'), n('a', 'number')], []));
  assert.equal(x, y);
});

test('payload carries only settings, never results or callbacks', () => {
  const p = toPayload([n('a', 'number', { data: { value: '5', result: 9, set() {} } })], []);
  assert.deepEqual(p.nodes[0].data, { value: '5' });
});

test('save/load keeps positions, values and wires exactly', () => {
  const original = {
    nodes: [n('a', 'number', { position: { x: 12.5, y: -40 }, data: { value: '7' } }), n('out', 'display', { position: { x: 300, y: 60 } })],
    edges: [wire('a', 'out', 'x')],
  };
  const stored = JSON.parse(JSON.stringify(toStored(original.nodes, original.edges)));
  const back = fromStored(stored);
  assert.deepEqual(back.nodes, original.nodes);
  assert.deepEqual(back.edges, original.edges);
});

test('formatValue', () => {
  assert.equal(formatValue(5), '5');
  assert.equal(formatValue(2.25), '2.25');
  assert.equal(formatValue(0.1 + 0.2), '0.3');
  assert.equal(formatValue(undefined), '—');
  assert.equal(formatValue(Infinity), '—');
});
