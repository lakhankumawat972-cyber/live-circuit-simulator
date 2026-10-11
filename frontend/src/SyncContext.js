import { createContext } from 'react';

// { phase, result, typeOf(nodeId) } - what the nodes need to show their live state.
export const SyncContext = createContext({ phase: 'pending', result: null, typeOf: () => '' });
