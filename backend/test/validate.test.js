import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ValidationError, validateGraphDocument, validateSimulateBody } from '../src/validate.js';

const node = (id, extra = {}) => ({ id, type: 'number', position: { x: 1, y: 2 }, data: { value: '5' }, ...extra });

test('a stored graph round-trips positions, values and wires', () => {
  const body = {
    name: 'demo',
    graph: {
      nodes: [node('a'), node('b', { type: 'display', data: {} })],
      edges: [{ id: 'e1', source: 'a', target: 'b', sourceHandle: 'out', targetHandle: 'x' }],
    },
  };
  assert.deepEqual(validateGraphDocument(body), body);
});

test('unknown fields (selection state, measured sizes, results) are dropped', () => {
  const doc = validateGraphDocument({ graph: { nodes: [node('a', { selected: true, measured: { width: 9 } })], edges: [] } });
  assert.deepEqual(Object.keys(doc.graph.nodes[0]).sort(), ['data', 'id', 'position', 'type']);
  assert.equal(doc.name, 'Untitled graph');
});

test('rejects malformed graphs', () => {
  const bad = [
    null,
    {},
    { graph: { nodes: 'x', edges: [] } },
    { graph: { nodes: [node('a'), node('a')], edges: [] } },
    { graph: { nodes: [node('a', { position: { x: 'left', y: 1 } })], edges: [] } },
    { graph: { nodes: [node('a', { data: { value: { nested: 1 } } })], edges: [] } },
    { graph: { nodes: [node('a', { data: { $where: '1' } })], edges: [] } },
    { graph: { nodes: [node('a', { data: { 'a.b': 1 } })], edges: [] } },
    { graph: { nodes: [node('a')], edges: [{ id: 'e', source: 'a' }] } },
    { name: '', graph: { nodes: [], edges: [] } },
    { graph: { nodes: Array.from({ length: 501 }, (_, i) => node(`n${i}`)), edges: [] } },
  ];
  for (const body of bad) assert.throws(() => validateGraphDocument(body), ValidationError, JSON.stringify(body)?.slice(0, 60));
});

test('simulate payload keeps only what the engine needs', () => {
  const out = validateSimulateBody({
    version: 7,
    nodes: [{ id: 'a', type: 'number', data: { value: '1' }, position: { x: 0, y: 0 } }],
    edges: [{ id: 'e', source: 'a', target: 'b', targetHandle: 'x', sourceHandle: 'out' }],
  });
  assert.deepEqual(out, {
    version: 7,
    nodes: [{ id: 'a', type: 'number', data: { value: '1' } }],
    edges: [{ source: 'a', target: 'b', targetHandle: 'x' }],
  });
});

test('simulate payload: version optional, must be an integer', () => {
  assert.equal(validateSimulateBody({ nodes: [] }).version, null);
  assert.throws(() => validateSimulateBody({ nodes: [], version: 'x' }), ValidationError);
  assert.throws(() => validateSimulateBody({ nodes: [], version: 1.5 }), ValidationError);
});

test('a formula with a newline is accepted by the API (the simulation service rejects it)', () => {
  const out = validateSimulateBody({ nodes: [{ id: 'f', type: 'formula', data: { expr: 'a\n.control' } }] });
  assert.equal(out.nodes[0].data.expr, 'a\n.control');
});
