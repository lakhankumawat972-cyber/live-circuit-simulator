"""Runs ngspice in batch mode and reads node voltages back.

Every failure mode is returned as a ``RunResult.state`` instead of raising, so
the engine can turn it into a clear status for the UI:

    ok          ngspice ran and printed values
    failed      ngspice ran but reported errors / printed nothing usable
    timeout     ngspice hung and was killed
    crashed     ngspice died from a signal
    unavailable the binary is missing
    busy        too many simulations already running
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field

# "name  value", "name = value" and "v(name) = value" lines, as printed by
# `.op` (the Node/Voltage table) and by `print`.
_VALUE_LINE = re.compile(
    r"^\s*(?:v\()?(?P<name>[a-z_][a-z0-9_#.]*)\)?\s*(?:=\s*)?"
    r"(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?|[-+]?inf(?:inity)?|[-+]?nan)\s*$",
    re.IGNORECASE,
)


@dataclass
class RunResult:
    state: str
    values: dict[str, float] = field(default_factory=dict)
    output: str = ""
    message: str = ""
    returncode: int | None = None


def parse_output(text: str) -> dict[str, float]:
    """Extract ``{net: voltage}`` from ngspice's batch output."""
    values: dict[str, float] = {}
    for line in text.splitlines():
        match = _VALUE_LINE.match(line)
        if match:
            try:
                values[match.group("name").lower()] = float(match.group("value"))
            except ValueError:
                continue
    return values


def error_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith(("error", "fatal")) or "singular matrix" in low or "too small" in low:
            lines.append(line.strip())
    return lines


class NgspiceRunner:
    def __init__(self, binary: str = "ngspice", timeout: float = 5.0, max_concurrent: int = 4):
        self.binary = binary
        self.timeout = timeout
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def run(self, netlist: str) -> RunResult:
        if not self._slots.acquire(timeout=self.timeout):
            return RunResult("busy", message="Simulator is busy, retrying")
        try:
            return self._run(netlist)
        finally:
            self._slots.release()

    def _run(self, netlist: str) -> RunResult:
        with tempfile.TemporaryDirectory(prefix="netlist-") as workdir:
            path = os.path.join(workdir, "circuit.cir")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(netlist)
            try:
                proc = subprocess.Popen(
                    [self.binary, "-b", path],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    cwd=workdir,
                    start_new_session=True,  # own process group so a hang can be killed whole
                )
            except FileNotFoundError:
                return RunResult("unavailable", message="ngspice is not installed")
            try:
                output, _ = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                self._kill(proc)
                proc.communicate()
                return RunResult("timeout", message=f"ngspice did not finish within {self.timeout:g}s and was stopped")

        if proc.returncode is not None and proc.returncode < 0:
            try:
                sig = signal.Signals(-proc.returncode).name
            except ValueError:
                sig = f"signal {-proc.returncode}"
            return RunResult("crashed", output=output, returncode=proc.returncode, message=f"ngspice crashed ({sig})")

        values = parse_output(output)
        errors = error_lines(output)
        if proc.returncode != 0 or not values:
            detail = errors[0] if errors else "ngspice produced no readable result"
            return RunResult("failed", values, output, detail, proc.returncode)
        return RunResult("ok", values, output, errors[0] if errors else "", proc.returncode)

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
