// Manual clock + controllable fetch for the syncer tests.

export function fakeClock() {
  let now = 0;
  let nextId = 1;
  const timers = new Map();
  return {
    setTimer(fn, ms) {
      const id = nextId++;
      timers.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimer(id) {
      timers.delete(id);
    },
    pending: () => timers.size,
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = due[1].at;
        due[1].fn();
        await flush();
      }
      now = end;
      await flush();
    },
  };
}

export const flush = () => new Promise((resolve) => setImmediate(resolve));

/** A fetch whose calls are resolved/rejected by hand. */
export function controllableFetch({ honourAbort = true } = {}) {
  const calls = [];
  const fetchFn = (url, init) =>
    new Promise((resolve, reject) => {
      const call = {
        url,
        body: JSON.parse(init.body),
        signal: init.signal,
        respond: (status, body) => resolve({ status, ok: status < 300, json: async () => body }),
        fail: (error = new TypeError('fetch failed')) => reject(error),
      };
      if (honourAbort) {
        init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      }
      calls.push(call);
    });
  return { fetchFn, calls };
}

export const okBody = (version, extra = {}) => ({
  version,
  nodes: {},
  loops: [],
  netlist: '',
  engine: { state: 'ok', message: '' },
  ...extra,
});
