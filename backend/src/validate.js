// Shape checks for everything that enters the API. Nothing here knows about
// node types: the simulation service owns that. The API only makes sure the
// payload is a well-formed, bounded graph before it is stored or forwarded.

export const LIMITS = { nodes: 500, edges: 2000, nameLength: 100, textLength: 1000 };

export class ValidationError extends Error {}

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

function text(value, label, max = 100) {
  if (typeof value !== 'string' || value.length === 0 || value.length > max) {
    throw new ValidationError(`${label} must be a text of 1-${max} characters`);
  }
  return value;
}

function optionalText(value, label) {
  return value === undefined || value === null ? null : text(value, label);
}

function list(value, label, max) {
  if (!Array.isArray(value)) throw new ValidationError(`${label} must be a list`);
  if (value.length > max) throw new ValidationError(`${label} has more than ${max} items`);
  return value;
}

// Node settings: flat object of text / number / boolean values. Keys that
// MongoDB treats as operators or paths ("$x", "a.b") are refused outright.
function nodeData(value) {
  if (value === undefined) return {};
  if (!isObject(value)) throw new ValidationError('node data must be an object');
  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (key.startsWith('$') || key.includes('.') || key.length > 40) {
      throw new ValidationError(`node data key "${key.slice(0, 20)}" is not allowed`);
    }
    if (item === null || typeof item === 'number' || typeof item === 'boolean') out[key] = item;
    else if (typeof item === 'string' && item.length <= LIMITS.textLength) out[key] = item;
    else throw new ValidationError(`node data "${key}" must be short text, a number or a boolean`);
  }
  return out;
}

function position(value) {
  if (!isObject(value) || !Number.isFinite(value.x) || !Number.isFinite(value.y)) {
    throw new ValidationError('node position needs numeric x and y');
  }
  return { x: value.x, y: value.y };
}

/** A graph to be stored: keeps positions, values and wires exactly. */
export function validateStoredGraph(graph) {
  if (!isObject(graph)) throw new ValidationError('graph must be an object');
  const ids = new Set();
  const nodes = list(graph.nodes, 'graph.nodes', LIMITS.nodes).map((n, i) => {
    if (!isObject(n)) throw new ValidationError(`node ${i} must be an object`);
    const id = text(n.id, `node ${i} id`);
    if (ids.has(id)) throw new ValidationError(`duplicate node id "${id.slice(0, 20)}"`);
    ids.add(id);
    return { id, type: text(n.type, `node ${i} type`, 40), position: position(n.position), data: nodeData(n.data) };
  });
  const edges = list(graph.edges, 'graph.edges', LIMITS.edges).map((e, i) => {
    if (!isObject(e)) throw new ValidationError(`wire ${i} must be an object`);
    return {
      id: text(e.id, `wire ${i} id`, 200),
      source: text(e.source, `wire ${i} source`),
      target: text(e.target, `wire ${i} target`),
      sourceHandle: optionalText(e.sourceHandle, `wire ${i} sourceHandle`),
      targetHandle: optionalText(e.targetHandle, `wire ${i} targetHandle`),
    };
  });
  return { nodes, edges };
}

export function validateGraphDocument(body) {
  if (!isObject(body)) throw new ValidationError('body must be an object');
  const name = body.name === undefined ? 'Untitled graph' : text(body.name, 'name', LIMITS.nameLength);
  return { name, graph: validateStoredGraph(body.graph) };
}

/** A graph to be simulated: only what the engine needs, no positions. */
export function validateSimulateBody(body) {
  if (!isObject(body)) throw new ValidationError('body must be an object');
  const nodes = list(body.nodes, 'nodes', LIMITS.nodes).map((n, i) => {
    if (!isObject(n)) throw new ValidationError(`node ${i} must be an object`);
    return { id: text(n.id, `node ${i} id`), type: text(n.type, `node ${i} type`, 40), data: nodeData(n.data) };
  });
  const edges = list(body.edges ?? [], 'edges', LIMITS.edges).map((e, i) => {
    if (!isObject(e)) throw new ValidationError(`wire ${i} must be an object`);
    return {
      source: text(e.source, `wire ${i} source`),
      target: text(e.target, `wire ${i} target`),
      targetHandle: optionalText(e.targetHandle, `wire ${i} targetHandle`),
    };
  });
  const version = body.version === undefined || body.version === null ? null : body.version;
  if (version !== null && !Number.isSafeInteger(version)) throw new ValidationError('version must be an integer');
  return { nodes, edges, version };
}
