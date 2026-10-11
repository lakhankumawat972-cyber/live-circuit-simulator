// Keeps the canvas in step with the backend.
//
// Rules this module enforces (they are what the tests check):
//  * edits are debounced, so typing 1, 10, 100 sends one request;
//  * at most ONE request is in flight: a newer edit aborts the older request;
//  * every request carries a version, and an answer is only used if it is for
//    the newest version, so even a response that slips past the abort (or
//    arrives out of order) can never overwrite newer results;
//  * if the API or the simulator is down or slow, the same graph is retried
//    with growing delays until it works, with no user action.
//
// onUpdate receives { phase, version, result?, message?, retryInMs? } where
// phase is 'pending' | 'ok' | 'degraded' | 'offline' | 'error'.

export const RETRY_DELAYS = [1000, 2000, 4000, 8000];

export function createSyncer({
  endpoint,
  onUpdate,
  fetchFn = (...args) => fetch(...args),
  debounceMs = 250,
  requestTimeoutMs = 15_000,
  retryDelays = RETRY_DELAYS,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  let latest = 0;
  let graph = null;
  let inflight = null;
  let debounceTimer = null;
  let retryTimer = null;
  let attempts = 0;
  let destroyed = false;

  const isStale = (version) => destroyed || version !== latest;

  function cancelWork() {
    if (debounceTimer !== null) clearTimer(debounceTimer);
    if (retryTimer !== null) clearTimer(retryTimer);
    debounceTimer = retryTimer = null;
    if (inflight) inflight.abort();
    inflight = null;
  }

  function scheduleRetry(version) {
    const delay = retryDelays[Math.min(attempts, retryDelays.length - 1)];
    attempts += 1;
    retryTimer = setTimer(() => {
      retryTimer = null;
      send(version);
    }, delay);
    return delay;
  }

  function degrade(phase, message, version, result = null) {
    const retryInMs = scheduleRetry(version);
    onUpdate({ phase, version, result, message, retryInMs });
  }

  async function send(version) {
    if (isStale(version)) return;
    const controller = new AbortController();
    inflight = controller;
    let timedOut = false;
    const timer = setTimer(() => {
      timedOut = true;
      controller.abort();
    }, requestTimeoutMs);
    try {
      const res = await fetchFn(endpoint, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ ...graph, version }),
        signal: controller.signal,
      });
      let body = null;
      try {
        body = await res.json();
      } catch {
        body = null;
      }
      if (isStale(version)) return; // a newer edit exists: this answer is old news
      if (body && body.version != null && body.version !== version) return; // out-of-order answer
      if (res.status >= 400 && res.status < 500) {
        onUpdate({ phase: 'error', version, message: body?.error ?? `Request rejected (${res.status})` });
        return;
      }
      const state = body?.engine?.state;
      if (state === 'ok') {
        attempts = 0;
        onUpdate({ phase: 'ok', version, result: body });
      } else if (state) {
        degrade('degraded', body.engine.message || `Simulator problem: ${state}`, version, body);
      } else {
        degrade('offline', 'Unexpected answer from the API', version);
      }
    } catch {
      if (isStale(version)) return; // aborted because a newer edit replaced this request
      degrade('offline', timedOut ? 'The API did not answer in time' : 'Cannot reach the API', version);
    } finally {
      clearTimer(timer);
      if (inflight === controller) inflight = null;
    }
  }

  return {
    /** Call with the current payload whenever the circuit changes. */
    push(nextGraph) {
      if (destroyed) return;
      latest += 1;
      graph = nextGraph;
      attempts = 0;
      cancelWork();
      const version = latest;
      onUpdate({ phase: 'pending', version });
      debounceTimer = setTimer(() => {
        debounceTimer = null;
        send(version);
      }, debounceMs);
    },
    /** Retry the current graph immediately (e.g. a "retry now" button). */
    retryNow() {
      if (destroyed || graph === null) return;
      cancelWork();
      send(latest);
    },
    destroy() {
      cancelWork();
      destroyed = true;
    },
  };
}
