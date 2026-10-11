// Client for the Python simulation service.
//
// It never throws: every way the service can misbehave (down, hanging, bad
// answer) becomes a normal response whose `engine.state` the UI understands,
// so the Node API itself and the graph endpoints are unaffected.

const down = (version, state, message, status = 503) => ({
  status,
  body: { version, nodes: {}, loops: [], netlist: '', engine: { state, message } },
});

export function createSimulationClient({ baseUrl, fetchFn = fetch, timeoutMs = 10_000 }) {
  return {
    /** @returns {Promise<{status:number, body:object}|{aborted:true}>} */
    async simulate(payload, { signal } = {}) {
      const { version } = payload;
      const timeout = new AbortController();
      const timer = setTimeout(() => timeout.abort(), timeoutMs);
      const combined = signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal;
      try {
        const res = await fetchFn(`${baseUrl}/simulate`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(payload),
          signal: combined,
        });
        let json;
        try {
          json = await res.json();
        } catch {
          return down(version, 'error', 'Simulation service sent an unreadable answer', 502);
        }
        if (res.ok) return { status: 200, body: json };
        if (res.status === 422) {
          return { status: 422, body: { error: String(json.detail ?? 'Graph rejected'), version } };
        }
        return down(version, 'error', 'Simulation service failed', 502);
      } catch {
        if (signal?.aborted) return { aborted: true }; // the browser gave up on this request
        if (timeout.signal.aborted) return down(version, 'timeout', 'Simulation service did not answer in time', 504);
        return down(version, 'unavailable', 'Simulation service is not reachable');
      } finally {
        clearTimeout(timer);
      }
    },
  };
}
