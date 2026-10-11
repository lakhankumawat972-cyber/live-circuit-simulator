import os
import shutil
import stat
import tempfile
import textwrap
import unittest

from app.engine import simulate
from app.runner import NgspiceRunner, parse_output

from .helpers import node, wire

TABLE = """
Circuit: * live graph netlist

Doing analysis at TEMP = 27.000000 and TNOM = 27.000000

No. of Data Rows : 1
Node                                  Voltage
----                                  -------
o_n1                                        2
o_n2                           3.000000000000000e+00
o_n3                                   -1.5e-05
vn1#branch                            -1.000000e-12
"""


class ParseTests(unittest.TestCase):
    def test_node_voltage_table(self):
        v = parse_output(TABLE)
        self.assertEqual(v["o_n1"], 2)
        self.assertEqual(v["o_n2"], 3)
        self.assertEqual(v["o_n3"], -1.5e-05)

    def test_print_style_lines(self):
        v = parse_output("v(o_n1) = 2.000000e+00\nO_N2 = -4\n")
        self.assertEqual(v, {"o_n1": 2.0, "o_n2": -4.0})

    def test_non_finite_values(self):
        v = parse_output("o_n1  inf\no_n2  -nan\no_n3  -Infinity\n")
        self.assertEqual(sorted(v), ["o_n1", "o_n2", "o_n3"])

    def test_ignores_noise(self):
        self.assertEqual(parse_output("Warning: stuff 12\nNo. of Data Rows : 1\nError: x\n"), {})


def fake_binary(directory, body):
    path = os.path.join(directory, "fake-ngspice")
    with open(path, "w") as handle:
        handle.write("#!/bin/sh\n" + textwrap.dedent(body))
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


@unittest.skipUnless(shutil.which("sh"), "needs a POSIX shell")
class RunnerFailureModes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_hang_is_killed_and_reported(self):
        runner = NgspiceRunner(fake_binary(self.dir, "sleep 30\n"), timeout=0.5)
        result = runner.run(".end\n")
        self.assertEqual(result.state, "timeout")

    def test_crash_is_reported(self):
        runner = NgspiceRunner(fake_binary(self.dir, "kill -SEGV $$\n"), timeout=5)
        result = runner.run(".end\n")
        self.assertEqual(result.state, "crashed")
        self.assertIn("SIGSEGV", result.message)

    def test_missing_binary(self):
        result = NgspiceRunner(os.path.join(self.dir, "nope"), timeout=1).run(".end\n")
        self.assertEqual(result.state, "unavailable")

    def test_nonzero_exit_is_failed_with_the_error_line(self):
        runner = NgspiceRunner(fake_binary(self.dir, "echo 'Error: no such device bn3'\nexit 1\n"), timeout=5)
        result = runner.run(".end\n")
        self.assertEqual(result.state, "failed")
        self.assertIn("bn3", result.message)

    def test_runs_through_the_engine_end_to_end(self):
        # a stand-in binary that prints a table; checks file passing + parsing
        binary = fake_binary(self.dir, "grep -q '^Vn1' \"$2\" && printf 'o_n1  7\\n'\n")
        r = simulate({"nodes": [node("n", "number", value="7"), node("d", "display")], "edges": [wire("n", "d")]},
                     NgspiceRunner(binary, timeout=5))
        self.assertEqual(r["nodes"]["d"]["value"], 7)

    def test_hang_through_the_engine_marks_engine_not_nodes(self):
        runner = NgspiceRunner(fake_binary(self.dir, "sleep 30\n"), timeout=0.5)
        r = simulate({"nodes": [node("n", "number", value="7"), node("d", "display")], "edges": [wire("n", "d")]}, runner)
        self.assertEqual(r["engine"]["state"], "timeout")
        self.assertEqual(r["nodes"]["d"]["status"], "unavailable")


@unittest.skipUnless(shutil.which("ngspice"), "ngspice is not installed (runs inside the Docker image)")
class RealNgspice(unittest.TestCase):
    """Acceptance graphs against the real binary: docker compose run --rm simulation-service python -m unittest"""

    def run_graph(self, nodes, edges):
        return simulate({"nodes": nodes, "edges": edges}, NgspiceRunner(timeout=10))

    def test_graphs_1_to_3_and_7(self):
        r = self.run_graph(
            [node("a", "number", value="2"), node("b", "number", value="3"), node("add", "add"), node("out", "display"),
             node("c", "number", value="4"), node("mul", "multiply"), node("o2", "display"),
             node("sq", "multiply"), node("o3", "display"), node("f", "formula", expr="a * 2 + b"), node("o4", "display"),
             node("seven", "number", value="7")],
            [wire("a", "add", "a"), wire("b", "add", "b"), wire("add", "out", "x"),
             wire("add", "mul", "a"), wire("c", "mul", "b"), wire("mul", "o2", "x"),
             wire("seven", "sq", "a"), wire("seven", "sq", "b"), wire("sq", "o3", "x"),
             wire("a", "f", "a"), wire("c", "f", "b"), wire("f", "o4", "x")],
        )
        self.assertEqual(r["engine"]["state"], "ok", r)
        self.assertEqual([r["nodes"][k]["value"] for k in ("out", "o2", "o3", "o4")], [5, 20, 49, 8])

    def test_divide(self):
        r = self.run_graph(
            [node("a", "number", value="20"), node("b", "number", value="4"), node("d", "divide"), node("o", "display")],
            [wire("a", "d", "a"), wire("b", "d", "b"), wire("d", "o", "x")],
        )
        self.assertEqual(r["nodes"]["o"]["value"], 5, r)


if __name__ == "__main__":
    unittest.main()
