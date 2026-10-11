import { Handle, Position, useReactFlow } from '@xyflow/react';
import { memo, useContext } from 'react';
import { formatValue } from '../graph.js';
import { NODE_DEFS, OUTPUT_HANDLE } from '../nodeDefs.js';
import { SyncContext } from '../SyncContext.js';

function Status({ type, entry, phase, typeOf }) {
  if (phase === 'offline' || !entry) return <div className="result muted">—</div>;
  if (entry.status === 'ok') {
    return <div className={`result ok ${type === 'display' ? 'big' : ''}`}>{type === 'display' ? '' : '= '}{formatValue(entry.value)}</div>;
  }
  if (entry.status === 'error') return <div className="result error" title={entry.kind}>⚠ {entry.message}</div>;
  if (entry.status === 'blocked') {
    return <div className="result blocked">⛔ Blocked: {NODE_DEFS[typeOf(entry.blockedBy)]?.label ?? 'a node'} upstream has an error</div>;
  }
  return <div className="result muted" title={entry.message}>— simulator unavailable</div>;
}

// One component draws every node type; NODE_DEFS says what differs.
function CircuitNode({ id, type, data, selected }) {
  const def = NODE_DEFS[type];
  const { updateNodeData } = useReactFlow();
  const { result, phase, typeOf } = useContext(SyncContext);
  const entry = result?.nodes?.[id];
  const status = phase === 'offline' ? 'unknown' : (entry?.status ?? 'unknown');
  const stale = phase === 'pending';

  return (
    <div className={`node status-${status} ${stale ? 'stale' : ''} ${selected ? 'selected' : ''}`}>
      <div className="node-title">{def.label}</div>

      {def.inputs.map((handle) => (
        <div className="port in" key={handle}>
          <Handle type="target" position={Position.Left} id={handle} />
          <span>{handle}</span>
        </div>
      ))}

      {type === 'number' && (
        <input
          className="nodrag"
          aria-label="Number value"
          inputMode="decimal"
          value={data.value ?? ''}
          onChange={(e) => updateNodeData(id, { value: e.target.value })}
        />
      )}
      {type === 'formula' && (
        <textarea
          className="nodrag nowheel"
          aria-label="Formula expression"
          rows={2}
          spellCheck={false}
          value={data.expr ?? ''}
          onChange={(e) => updateNodeData(id, { expr: e.target.value })}
        />
      )}

      <Status type={type} entry={entry} phase={phase} typeOf={typeOf} />

      {def.output && (
        <div className="port out">
          <span>out</span>
          <Handle type="source" position={Position.Right} id={OUTPUT_HANDLE} />
        </div>
      )}
    </div>
  );
}

export default memo(CircuitNode);
