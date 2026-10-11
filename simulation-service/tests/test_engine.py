"""Graph execution tests. The acceptance graphs are numbered as in the task."""

import unittest

from app.engine import GraphFormatError, simulate
from app.runner import RunResult

from .helpers import FakeSpice, RaisingRunner, node, wire


def run(nodes, edges, runner=None):
    return simulate({"nodes": nodes, "edges": edges}, runner or FakeSpice())


def value(result, node_id):
    entry = result["nodes"][node_id]
    assert entry["status"] == "ok", entry
    return entry["value"]


class AcceptanceGraphs(unittest.TestCase):
    def test_1_add(self):
        r = run(
            [node("a", "number", value="2"), node("b", "number", value="3"), node("add", "add"), node("out", "display")],
            [wire("a", "add", "a"), wire("b", "add", "b"), wire("add", "out", "x")],
        )
        self.assertEqual(value(r, "out"), 5)
        self.assertEqual(r["engine"]["state"], "ok")

    def test_2_add_then_multiply(self):
        r = run(
            [node("a", "number", value="2"), node("b", "number", value="3"), node("c", "number", value="4"),
             node("add", "add"), node("mul", "multiply"), node("out", "display")],
            [wire("a", "add", "a"), wire("b", "add", "b"), wire("add", "mul", "a"), wire("c", "mul", "b"), wire("mul", "out", "x")],
        )
        self.assertEqual(value(r, "out"), 20)

    def test_3_one_number_into_both_inputs(self):
        r = run(
            [node("n", "number", value="7"), node("mul", "multiply"), node("out", "display")],
            [wire("n", "mul", "a"), wire("n", "mul", "b"), wire("mul", "out", "x")],
        )
        self.assertEqual(value(r, "out"), 49)

    def test_4_divide_by_zero(self):
        r = run(
            [node("a", "number", value="10"), node("z", "number", value="0"), node("div", "divide"), node("out", "display")],
            [wire("a", "div", "a"), wire("z", "div", "b"), wire("div", "out", "x")],
        )
        self.assertEqual(r["nodes"]["div"]["status"], "error")
        self.assertEqual(r["nodes"]["div"]["kind"], "divide_by_zero")
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")
        self.assertEqual(r["nodes"]["out"]["blockedBy"], "div")
        self.assertNotIn("value", r["nodes"]["out"])
        self.assertEqual(value(r, "a"), 10)  # unrelated nodes still evaluate

    def test_5_add_with_one_input_wired(self):
        r = run(
            [node("a", "number", value="1"), node("add", "add"), node("out", "display")],
            [wire("a", "add", "a"), wire("add", "out", "x")],
        )
        self.assertEqual(r["nodes"]["add"]["status"], "error")
        self.assertEqual(r["nodes"]["add"]["kind"], "missing_input")
        self.assertIn("b", r["nodes"]["add"]["message"])
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")

    def test_6_loop(self):
        r = run(
            [node("n", "number", value="1"), node("add", "add"), node("mul", "multiply"), node("out", "display")],
            [wire("n", "add", "a"), wire("mul", "add", "b"), wire("add", "mul", "a"), wire("n", "mul", "b"), wire("mul", "out", "x")],
        )
        self.assertEqual(r["nodes"]["add"]["kind"], "loop")
        self.assertEqual(r["nodes"]["mul"]["kind"], "loop")
        self.assertEqual(r["loops"], [["add", "mul"]])
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")
        self.assertEqual(value(r, "n"), 1)

    def test_7_formula(self):
        r = run(
            [node("a", "number", value="3"), node("b", "number", value="4"), node("f", "formula", expr="a * 2 + b"), node("out", "display")],
            [wire("a", "f", "a"), wire("b", "f", "b"), wire("f", "out", "x")],
        )
        self.assertEqual(value(r, "out"), 10)

    def test_8_unsafe_formula_never_reaches_ngspice(self):
        spy = FakeSpice()
        r = run(
            [node("a", "number", value="3"), node("b", "number", value="4"),
             node("f", "formula", expr="a + b\n.control\nshell ls"), node("out", "display")],
            [wire("a", "f", "a"), wire("b", "f", "b"), wire("f", "out", "x")],
            spy,
        )
        self.assertEqual(r["nodes"]["f"]["kind"], "invalid_formula")
        self.assertIn("new line", r["nodes"]["f"]["message"])
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")
        for netlist in spy.netlists:  # FakeSpice already rejects unknown lines; double check
            self.assertNotIn("control", netlist)
            self.assertNotIn("shell", netlist)

    def test_8b_only_unsafe_graph_does_not_call_ngspice_at_all(self):
        r = run([node("f", "formula", expr="a\n.control")], [], RaisingRunner())
        self.assertEqual(r["nodes"]["f"]["kind"], "invalid_formula")


class NetlistShape(unittest.TestCase):
    def test_lines_follow_the_task_mapping(self):
        r = run(
            [node("a", "number", value="2"), node("b", "number", value="3"), node("add", "add"), node("out", "display")],
            [wire("a", "add", "a"), wire("b", "add", "b"), wire("add", "out", "x")],
        )
        lines = r["netlist"].splitlines()
        self.assertIn("Vn1 o_n1 0 DC 2.0", lines)
        self.assertIn("Vn2 o_n2 0 DC 3.0", lines)
        self.assertIn("Bn3 o_n3 0 V = V(o_n1) + V(o_n2)", lines)
        self.assertEqual(lines[-2:], [".op", ".end"])
        self.assertFalse(any(line.startswith("Bn4") or line.startswith("Vn4") for line in lines))  # Display: no line

    def test_works_for_graphs_not_known_in_advance(self):
        # (1 + 2) * 3 / 4 fan-out into two displays; wiring order shuffled
        nodes = [node("d1", "display"), node("div", "divide"), node("k4", "number", value="4"), node("mul", "multiply"),
                 node("k3", "number", value="3"), node("add", "add"), node("k1", "number", value="1"),
                 node("k2", "number", value="2"), node("d2", "display")]
        edges = [wire("div", "d1", "x"), wire("mul", "div", "a"), wire("k4", "div", "b"), wire("add", "mul", "a"),
                 wire("k3", "mul", "b"), wire("k1", "add", "a"), wire("k2", "add", "b"), wire("mul", "d2", "x")]
        r = run(nodes, edges)
        self.assertEqual(value(r, "d1"), 2.25)
        self.assertEqual(value(r, "d2"), 9)

    def test_odd_node_ids_never_reach_the_netlist(self):
        r = run(
            [node("x y;\n.end", "number", value="2"), node("o'ut", "display")],
            [{"source": "x y;\n.end", "target": "o'ut"}],
        )
        self.assertEqual(value(r, "o'ut"), 2)
        self.assertNotIn("x y", r["netlist"])


class ErrorHandling(unittest.TestCase):
    def test_empty_graph(self):
        self.assertEqual(run([], [])["nodes"], {})

    def test_blocking_follows_the_whole_chain_and_not_siblings(self):
        r = run(
            [node("a", "number", value="1"), node("add", "add"), node("m", "multiply"), node("k", "number", value="2"),
             node("out", "display"), node("ok", "display")],
            [wire("a", "add", "a"), wire("add", "m", "a"), wire("k", "m", "b"), wire("m", "out", "x"), wire("k", "ok", "x")],
        )
        self.assertEqual(r["nodes"]["add"]["status"], "error")
        self.assertEqual(r["nodes"]["m"]["blockedBy"], "add")
        self.assertEqual(r["nodes"]["out"]["blockedBy"], "add")
        self.assertEqual(value(r, "ok"), 2)

    def test_divide_by_zero_deep_in_the_graph(self):
        r = run(
            [node("a", "number", value="5"), node("b", "number", value="5"), node("sub", "formula", expr="a - b"),
             node("div", "divide"), node("k", "number", value="1"), node("out", "display")],
            [wire("a", "sub", "a"), wire("b", "sub", "b"), wire("k", "div", "a"), wire("sub", "div", "b"), wire("div", "out", "x")],
        )
        self.assertEqual(r["nodes"]["div"]["kind"], "divide_by_zero")
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")
        self.assertEqual(value(r, "sub"), 0)

    def test_formula_division_by_zero(self):
        r = run(
            [node("a", "number", value="1"), node("b", "number", value="0"), node("f", "formula", expr="a / b")],
            [wire("a", "f", "a"), wire("b", "f", "b")],
        )
        self.assertEqual(r["nodes"]["f"]["kind"], "divide_by_zero")

    def test_fixing_the_problem_clears_it(self):
        broken = run([node("n", "number", value="abc")], [])
        self.assertEqual(broken["nodes"]["n"]["kind"], "invalid_value")
        fixed = run([node("n", "number", value="12")], [])
        self.assertEqual(value(fixed, "n"), 12)

    def test_bad_numbers(self):
        for raw in ["", " ", "abc", "1_0", "nan", "inf", "1e999", "0x10", None, True, "1e16"]:
            with self.subTest(raw=raw):
                r = run([node("n", "number", value=raw)], [])
                self.assertEqual(r["nodes"]["n"]["kind"], "invalid_value")

    def test_accepts_numbers_as_text_or_number(self):
        for raw, expected in [("2.5", 2.5), (3, 3), (" -4 ", -4), ("1e3", 1000), (".5", 0.5)]:
            with self.subTest(raw=raw):
                self.assertEqual(value(run([node("n", "number", value=raw)], []), "n"), expected)

    def test_unwired_display_and_formula_input(self):
        r = run([node("d", "display"), node("f", "formula", expr="a + b"), node("a", "number", value="1")], [wire("a", "f", "a")])
        self.assertEqual(r["nodes"]["d"]["kind"], "missing_input")
        self.assertEqual(r["nodes"]["f"]["kind"], "missing_input")
        self.assertIn("b", r["nodes"]["f"]["message"])

    def test_formula_only_needs_inputs_it_uses(self):
        r = run([node("a", "number", value="4"), node("f", "formula", expr="a * 2")], [wire("a", "f", "a")])
        self.assertEqual(value(r, "f"), 8)

    def test_second_wire_into_one_input_is_flagged(self):
        r = run(
            [node("a", "number", value="1"), node("b", "number", value="2"), node("d", "display")],
            [wire("a", "d", "x"), wire("b", "d", "x")],
        )
        self.assertEqual(r["nodes"]["d"]["kind"], "multiple_wires")

    def test_unknown_type_and_dangling_edges(self):
        r = run([node("q", "teleport"), node("a", "number", value="1")], [wire("a", "ghost", "x"), wire("ghost", "a")])
        self.assertEqual(r["nodes"]["q"]["kind"], "unknown_type")
        self.assertEqual(value(r, "a"), 1)

    def test_malformed_requests_are_rejected(self):
        for payload in [{}, {"nodes": "x"}, {"nodes": [1]}, {"nodes": [{"id": ""}]},
                        {"nodes": [{"id": "a"}, {"id": "a"}]}, {"nodes": [], "edges": 5}]:
            with self.subTest(payload=payload):
                with self.assertRaises(GraphFormatError):
                    simulate(payload, FakeSpice())


class NgspiceMisbehaves(unittest.TestCase):
    GRAPH = (
        [node("a", "number", value="2"), node("b", "number", value="3"), node("add", "add"), node("out", "display"), node("bad", "add")],
        [wire("a", "add", "a"), wire("b", "add", "b"), wire("add", "out", "x")],
    )

    class Stub:
        def __init__(self, result):
            self.result, self.calls = result, 0

        def run(self, netlist):
            self.calls += 1
            return self.result

    def check_engine_state(self, result, state):
        r = run(*self.GRAPH, runner=self.Stub(result))
        self.assertEqual(r["engine"]["state"], state)
        self.assertEqual(r["nodes"]["out"]["status"], "unavailable")
        self.assertNotIn("value", r["nodes"]["out"])
        # problems that need no ngspice are still reported on the right node
        self.assertEqual(r["nodes"]["bad"]["kind"], "missing_input")

    def test_timeout(self):
        self.check_engine_state(RunResult("timeout", message="stopped"), "timeout")

    def test_crash(self):
        self.check_engine_state(RunResult("crashed", message="boom"), "crashed")

    def test_not_installed(self):
        self.check_engine_state(RunResult("unavailable", message="missing"), "unavailable")

    def test_busy(self):
        self.check_engine_state(RunResult("busy", message="busy"), "busy")

    def test_unattributable_failure(self):
        self.check_engine_state(RunResult("failed", output="Error: something odd", message="Error: something odd"), "error")

    def test_error_naming_a_node_lands_on_that_node_and_the_rest_is_rerun(self):
        calls = []

        class Runner:
            def run(self, netlist):
                calls.append(netlist)
                if "Bn3" in netlist:
                    return RunResult("failed", output="Error: singular matrix at bn3", message="singular matrix", returncode=1)
                return FakeSpice().run(netlist)

        r = run(*self.GRAPH, runner=Runner())
        self.assertEqual(r["nodes"]["add"]["kind"], "ngspice_error")
        self.assertIn("singular matrix", r["nodes"]["add"]["message"])
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")
        self.assertEqual(r["engine"]["state"], "ok")
        self.assertEqual(value(r, "a"), 2)
        self.assertEqual(len(calls), 2)

    def test_ngspice_division_by_zero_error_is_attributed(self):
        # a hidden zero (a - b) feeding Divide: the pre-check catches it first,
        # but the same graph must behave when ngspice reports the error itself.
        nodes = [node("a", "number", value="1"), node("b", "number", value="2"), node("div", "divide"), node("out", "display")]
        edges = [wire("a", "div", "a"), wire("b", "div", "b"), wire("div", "out", "x")]

        class Runner:
            def run(self, netlist):
                return RunResult("failed", output="Error: division by zero in bn3", message="x", returncode=1)

        r = run(nodes, edges, Runner())
        self.assertEqual(r["nodes"]["div"]["kind"], "ngspice_error")
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")

    def test_non_finite_value_from_ngspice_marks_the_node(self):
        class Runner:
            def run(self, netlist):
                real = FakeSpice().run(netlist)
                real.values["o_n3"] = float("inf")
                return real

        r = run(*self.GRAPH, runner=Runner())
        self.assertEqual(r["nodes"]["add"]["kind"], "non_finite")
        self.assertEqual(r["nodes"]["out"]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
