import { NODE_DEFS, NODE_TYPES } from './nodeDefs.js';

export const DRAG_TYPE = 'application/x-circuit-node';

export default function Palette({ onAdd }) {
  return (
    <aside className="palette">
      <h2>Nodes</h2>
      <p className="hint">Drag onto the canvas, or click to add.</p>
      {NODE_TYPES.map((type) => (
        <div
          key={type}
          className="palette-item"
          draggable
          role="button"
          tabIndex={0}
          onDragStart={(e) => {
            e.dataTransfer.setData(DRAG_TYPE, type);
            e.dataTransfer.effectAllowed = 'move';
          }}
          onClick={() => onAdd(type)}
          onKeyDown={(e) => e.key === 'Enter' && onAdd(type)}
        >
          {NODE_DEFS[type].label}
          <small>
            {NODE_DEFS[type].inputs.length ? NODE_DEFS[type].inputs.join(', ') : 'no inputs'} → {NODE_DEFS[type].output ? 'out' : 'no output'}
          </small>
        </div>
      ))}
    </aside>
  );
}
