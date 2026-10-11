// Pure helpers for the graph: what is sent to the API, what is stored, and
// which connections are allowed. No React in here, so it is easy to test.

import { NODE_DEFS, OUTPUT_HANDLE } from './nodeDefs.js';

const SETTINGS = ['value', 'expr'];

/** The part of the graph that affects results (no positions, no selection). */
export function toPayload(nodes, edges) {
  return {
    nodes: nodes.map((n) => {
      const data = {};
      for (const key of SETTINGS) if (n.data?.[key] !== undefined) data[key] = n.data[key];
      return { id: n.id, type: n.type, data };
    }),
    edges: edges.map((e) => ({ source: e.source, target: e.target, targetHandle: e.targetHandle ?? null })),
  };
}

/** Same string for the same circuit, whatever order or selection state. */
export function signature(payload) {
  const byId = (a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const wire = (e) => `${e.source}>${e.target}:${e.targetHandle}`;
  return JSON.stringify({
    nodes: [...payload.nodes].sort(byId),
    edges: payload.edges.map(wire).sort(),
  });
}

/** Wiring rules: output -> input only, no self loops, one wire per input. */
export function canConnect(connection, nodes, edges) {
  const { source, target, sourceHandle, targetHandle } = connection;
  if (!source || !target || source === target) return false;
  const from = nodes.find((n) => n.id === source);
  const to = nodes.find((n) => n.id === target);
  if (!from || !to) return false;
  if (!NODE_DEFS[from.type]?.output || sourceHandle !== OUTPUT_HANDLE) return false;
  if (!NODE_DEFS[to.type]?.inputs.includes(targetHandle)) return false;
  return !edges.some((e) => e.target === target && e.targetHandle === targetHandle);
}

/** What gets saved: positions, values and wires, nothing transient. */
export function toStored(nodes, edges) {
  return {
    nodes: nodes.map((n) => ({ id: n.id, type: n.type, position: { x: n.position.x, y: n.position.y }, data: { ...n.data } })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? null,
      targetHandle: e.targetHandle ?? null,
    })),
  };
}

export function fromStored(graph) {
  return {
    nodes: graph.nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: n.data ?? {} })),
    edges: graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle ?? undefined,
      targetHandle: e.targetHandle ?? undefined,
    })),
  };
}

export function formatValue(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return String(Number(value.toPrecision(10)));
}
