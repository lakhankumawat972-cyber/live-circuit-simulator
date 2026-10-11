// What the editor knows about each node type: its title, its input handles,
// whether it has an output, and the settings a fresh node starts with.
// (The matching backend entry is simulation-service/app/nodes.py.)
//
// Handle ids are part of the saved graph and of the API contract:
// inputs are the names listed here, the single output is always "out".

export const OUTPUT_HANDLE = 'out';

export const NODE_DEFS = {
  number: { label: 'Number', inputs: [], output: true, defaults: () => ({ value: '0' }) },
  add: { label: 'Add', inputs: ['a', 'b'], output: true, defaults: () => ({}) },
  multiply: { label: 'Multiply', inputs: ['a', 'b'], output: true, defaults: () => ({}) },
  divide: { label: 'Divide', inputs: ['a', 'b'], output: true, defaults: () => ({}) },
  display: { label: 'Display', inputs: ['x'], output: false, defaults: () => ({}) },
  formula: { label: 'Formula', inputs: ['a', 'b'], output: true, defaults: () => ({ expr: 'a * 2 + b' }) },
};

export const NODE_TYPES = Object.keys(NODE_DEFS);
