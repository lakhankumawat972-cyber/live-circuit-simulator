# Live Node Graph Engine

Browser node editor where a Python service runs the whole graph through **ngspice** and the canvas stays in sync as you edit.
Stack: React + React Flow · Node/Express · Python/FastAPI + `ngspice -b` · MongoDB · Docker Compose.

## Run
```
docker compose up --build        # then open http://localhost:5173
```
Ports: UI 5173, Node API 5000, simulation service 8000 (MongoDB stays internal). No `.env` needed, no secrets in the repo.
Tests: `docker compose run --rm simulation-service python -m unittest discover -s tests -t .` ·
`docker compose run --rm backend npm test` · `docker compose run --rm frontend npm test`

## Architecture
```
 Browser (React Flow) ──► Node API (Express) ──► Python service (FastAPI) ──► ngspice -b
   syncer: debounce,        validates, stores        checks → netlist →         one process per run,
   abort, version check     graphs, proxies          run → map errors           hard timeout, killed on hang
                                 │
                                 └──► MongoDB (save / load)
```
The browser only talks to the Node API; only the Python service runs ngspice.

## Graph → netlist, and loop detection
`engine.py` reads the nodes/wires, then each node type in `nodes.py` contributes one line using the task's mapping
(`V<id> <out> 0 DC <v>`, `B<id> <out> 0 V = V(<a>) <op> V(<b>)`, nothing for Display). Every node owns one output net (`o_n3`);
a wire is simply "this input uses that net", so any graph works with no per-graph code. The netlist ends with `.op` / `.end`;
values are read from ngspice's output table. Node ids from the browser never appear in the netlist (they become `n1, n2…`).
**Loops:** Tarjan's strongly-connected-components (`graph.py`, iterative). Every node in a cycle is flagged `loop`;
nodes merely downstream of it are *blocked*, not flagged. Done before ngspice runs.

## Step 5
1. **Fast edits.** The syncer debounces 250 ms, keeps one request in flight (a newer edit aborts the older one, and the Node API cancels its upstream call), and stamps each request with a version. An answer is applied only if it is for the newest version, so out-of-order responses are dropped. Unit-tested with a fake clock/fetch.
2. **Errors on the right node.** Before ngspice: bad numbers, unwired inputs, loops, rejected formulas, and a Python reference pass that catches divide-by-zero. After: non-finite results, and ngspice error text is scanned for element/net names (`bn3`, `o_n3`) and mapped back to that node. Everything downstream of a broken node is `blocked` (never a stale value), and the failing node is removed and the rest re-run.
3. **ngspice misbehaves.** Run with a 5 s timeout in its own process group (SIGKILL on hang); crash, missing binary, and "busy" are distinct `engine.state`s. The Node API never throws on a bad/slow/down upstream: it answers 503/504 with an engine state. The UI shows a banner, clears values, and retries the same graph with backoff (1→8 s) until it recovers; Mongo being down only disables Save/Load. Containers restart on failure.
4. **Untrusted formulas.** `formula.py` is a tokenizer + parser that accepts only numbers, `a`, `b`, `+ - * /`, brackets, spaces/tabs. A new line or anything else is rejected with a message naming the character. Accepted formulas are **re-generated from the parsed tree**, fully bracketed, so user text never reaches the netlist. The node is marked in error and never sent to ngspice.

**One case that still breaks:** when the browser aborts a request, Node cancels the call to Python, but the ngspice run already started there continues until it finishes (≤ 5 s). A very slow ngspice plus constant editing can therefore fill the 4 run slots and show a transient "simulator busy" state. Fix: cancel runs on client disconnect.

## Extras
Wires can be re-dragged to reconnect; live netlist panel (button "Netlist"); Formula only requires the inputs it uses; save updates the same document; stored graph is validated and sanitised (Mongo operator keys refused).

## Adding a node type (e.g. Subtract)
Two entries: `simulation-service/app/nodes.py` (`NODE_TYPES`: inputs, netlist line, reference `evaluate`) and `frontend/src/nodeDefs.js` (`NODE_DEFS`). The palette, node drawing, wiring rules, validation and tests' helpers pick it up; add a test in `tests/test_engine.py`.

## What I'd do next
Cancel in-flight ngspice runs on disconnect; a persistent ngspice process or pooled workers for lower latency; undo/redo; more nodes (Subtract, Min/Max, Constant-π, 3-input Sum); show per-wire values; e2e browser tests; production build served by nginx instead of the Vite dev server; auth on the graph API.

## AI usage note
Claude (via Claude Code) was used to scaffold and write the code, tests and this README from the task text; I reviewed the design decisions (netlist construction, version-guarded sync, error mapping, formula whitelist) and can explain every file.
