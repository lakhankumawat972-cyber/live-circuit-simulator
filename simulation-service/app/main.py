"""FastAPI wrapper. All logic lives in engine.py; this file only does HTTP."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .engine import GraphFormatError, simulate
from .runner import NgspiceRunner

app = FastAPI(title="Live Circuit Simulation Service")
runner = NgspiceRunner(
    binary=os.environ.get("NGSPICE_BIN", "ngspice"),
    timeout=float(os.environ.get("NGSPICE_TIMEOUT", "5")),
    max_concurrent=int(os.environ.get("NGSPICE_MAX_CONCURRENT", "4")),
)


class GraphIn(BaseModel):
    nodes: list[dict]
    edges: list[dict] = Field(default_factory=list)
    version: int | None = None  # echoed back so the client can discard stale answers


@app.get("/health")
def health():
    return {"ok": True, "service": "simulation", "ngspice": runner.available()}


# A plain `def` endpoint runs in FastAPI's thread pool, so a slow ngspice run
# never blocks the event loop (or /health).
@app.post("/simulate")
def simulate_graph(graph: GraphIn):
    try:
        result = simulate(graph.model_dump(), runner)
    except GraphFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    result["version"] = graph.version
    return result
