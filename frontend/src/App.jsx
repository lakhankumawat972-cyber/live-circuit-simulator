import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  reconnectEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { SIMULATE_URL, listGraphs, loadGraph, saveGraph } from './api.js';
import { canConnect, fromStored, signature, toPayload, toStored } from './graph.js';
import CircuitNode from './nodes/CircuitNode.jsx';
import { NODE_DEFS, NODE_TYPES } from './nodeDefs.js';
import Palette, { DRAG_TYPE } from './Palette.jsx';
import { SyncContext } from './SyncContext.js';
import { createSyncer } from './syncer.js';

// Defined once: React Flow warns (and re-mounts nodes) if this object changes.
const nodeTypes = Object.fromEntries(NODE_TYPES.map((type) => [type, CircuitNode]));

// crypto.randomUUID only exists in secure contexts (https / localhost).
const shortId = () => (globalThis.crypto?.randomUUID ? crypto.randomUUID().slice(0, 8) : Math.random().toString(36).slice(2, 10));
const newId = (type) => `${type}_${shortId()}`;
const makeNode = (type, position) => ({ id: newId(type), type, position, data: NODE_DEFS[type].defaults() });

// A small starting circuit: 2 + 3 -> Display.
function starter() {
  const a = makeNode('number', { x: 60, y: 60 });
  const b = makeNode('number', { x: 60, y: 200 });
  const add = makeNode('add', { x: 300, y: 110 });
  const out = makeNode('display', { x: 520, y: 120 });
  a.data.value = '2';
  b.data.value = '3';
  const wire = (s, t, h) => ({ id: `e_${s.id}_${t.id}_${h}`, source: s.id, target: t.id, sourceHandle: 'out', targetHandle: h });
  return { nodes: [a, b, add, out], edges: [wire(a, add, 'a'), wire(b, add, 'b'), wire(add, out, 'x')] };
}

const ENGINE_TEXT = {
  timeout: 'ngspice timed out',
  crashed: 'ngspice crashed',
  unavailable: 'ngspice / simulation service unavailable',
  busy: 'simulator busy',
  error: 'simulator error',
};

function badge(sync, problems) {
  switch (sync.phase) {
    case 'pending':
      return { cls: 'pending', text: 'Syncing…' };
    case 'ok':
      return problems ? { cls: 'warn', text: `Live · ${problems} node${problems > 1 ? 's' : ''} need attention` } : { cls: 'ok', text: 'Live' };
    case 'degraded':
      return { cls: 'bad', text: `${ENGINE_TEXT[sync.result?.engine?.state] ?? 'Simulator problem'} - retrying automatically` };
    case 'offline':
      return { cls: 'bad', text: `${sync.message} - retrying automatically` };
    default:
      return { cls: 'bad', text: sync.message ?? 'Error' };
  }
}

function Editor() {
  const initial = useMemo(starter, []);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);
  const { screenToFlowPosition, fitView } = useReactFlow();

  const [name, setName] = useState('My graph');
  const [graphId, setGraphId] = useState(null);
  const [saved, setSaved] = useState([]);
  const [notice, setNotice] = useState('');
  const [showNetlist, setShowNetlist] = useState(false);
  const [sync, setSync] = useState({ phase: 'pending', result: null });

  // ---- live sync: every change to the circuit goes through the syncer ----
  const [syncer] = useState(() =>
    createSyncer({
      endpoint: SIMULATE_URL,
      onUpdate: (update) =>
        setSync((prev) => ({
          ...update,
          // while waiting for the next answer keep drawing the last one (dimmed)
          result: update.phase === 'pending' ? prev.result : update.result,
        })),
    }),
  );
  useEffect(() => () => syncer.destroy(), [syncer]);

  const payload = useMemo(() => toPayload(nodes, edges), [nodes, edges]);
  const sig = useMemo(() => signature(payload), [payload]);
  const payloadRef = useRef(payload);
  payloadRef.current = payload;
  // Re-runs only when the circuit itself changes - not on drag or selection.
  useEffect(() => {
    syncer.push(payloadRef.current);
  }, [sig, syncer]);

  // ---- wiring rules ----
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  nodesRef.current = nodes;
  edgesRef.current = edges;
  const isValidConnection = useCallback((c) => canConnect(c, nodesRef.current, edgesRef.current), []);
  const onConnect = useCallback(
    (c) => {
      if (canConnect(c, nodesRef.current, edgesRef.current)) setEdges((es) => addEdge(c, es));
    },
    [setEdges],
  );
  const onReconnect = useCallback((oldEdge, c) => setEdges((es) => reconnectEdge(oldEdge, c, es)), [setEdges]);

  // ---- adding nodes ----
  const addNode = useCallback(
    (type, position) => {
      const at = position ?? { x: 200 + Math.random() * 200, y: 80 + Math.random() * 240 };
      setNodes((ns) => [...ns, makeNode(type, at)]);
    },
    [setNodes],
  );
  const onDragOver = useCallback((e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);
  const onDrop = useCallback(
    (e) => {
      e.preventDefault();
      const type = e.dataTransfer.getData(DRAG_TYPE);
      if (NODE_DEFS[type]) addNode(type, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
    },
    [addNode, screenToFlowPosition],
  );

  // ---- save / load ----
  const refreshSaved = useCallback(() => listGraphs().then(setSaved).catch(() => setSaved([])), []);
  useEffect(() => {
    refreshSaved();
  }, [refreshSaved]);

  const onSave = async () => {
    try {
      const doc = await saveGraph({ id: graphId, name, graph: toStored(nodes, edges) });
      setGraphId(doc.id);
      setNotice(`Saved "${doc.name}"`);
      refreshSaved();
    } catch (err) {
      setNotice(`Save failed: ${err.message}`);
    }
  };
  const onLoad = async (id) => {
    if (!id) return;
    try {
      const doc = await loadGraph(id);
      const g = fromStored(doc.graph);
      setNodes(g.nodes);
      setEdges(g.edges);
      setName(doc.name);
      setGraphId(doc.id);
      setNotice(`Loaded "${doc.name}"`);
      setTimeout(() => fitView({ duration: 200 }), 50);
    } catch (err) {
      setNotice(`Load failed: ${err.message}`);
    }
  };
  const onNew = () => {
    setNodes([]);
    setEdges([]);
    setGraphId(null);
    setName('Untitled graph');
    setNotice('');
  };

  // ---- what to draw ----
  const typeById = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n.type])), [nodes]);
  const ctx = useMemo(
    () => ({ phase: sync.phase, result: sync.result, typeOf: (id) => typeById[id] }),
    [sync.phase, sync.result, typeById],
  );
  const shownEdges = useMemo(
    () =>
      edges.map((e) => {
        const s = sync.result?.nodes?.[e.source]?.status;
        return s === 'error' || s === 'blocked' ? { ...e, className: 'edge-bad' } : e;
      }),
    [edges, sync.result],
  );
  const problems = sync.result ? Object.values(sync.result.nodes).filter((n) => n.status === 'error').length : 0;
  const state = badge(sync, problems);

  return (
    <div className="app">
      <header>
        <h1>Live Node Graph Engine</h1>
        <input className="name" value={name} onChange={(e) => setName(e.target.value)} aria-label="Graph name" />
        <button onClick={onSave}>Save</button>
        <select value="" onChange={(e) => onLoad(e.target.value)} onFocus={refreshSaved} aria-label="Load a saved graph">
          <option value="">Load…</option>
          {saved.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <button onClick={onNew}>New</button>
        <button className={showNetlist ? 'active' : ''} onClick={() => setShowNetlist((v) => !v)}>
          Netlist
        </button>
        <span className={`badge ${state.cls}`} role="status">
          {state.text}
        </span>
        {notice && <span className="notice">{notice}</span>}
      </header>

      <div className="workspace">
        <Palette onAdd={(type) => addNode(type)} />
        <div className="canvas">
          <SyncContext.Provider value={ctx}>
            <ReactFlow
              nodes={nodes}
              edges={shownEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onReconnect={onReconnect}
              isValidConnection={isValidConnection}
              onDrop={onDrop}
              onDragOver={onDragOver}
              deleteKeyCode={['Backspace', 'Delete']}
              fitView
              proOptions={{ hideAttribution: true }}
            >
              <Background />
              <Controls />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </SyncContext.Provider>
          {showNetlist && <pre className="netlist">{sync.result?.netlist || '(no netlist yet)'}</pre>}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}
