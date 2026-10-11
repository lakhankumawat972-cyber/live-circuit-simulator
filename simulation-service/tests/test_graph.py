import unittest

from app.graph import downstream, find_loops, topological_order


def succ(*pairs):
    out = {}
    for a, b in pairs:
        out.setdefault(a, set()).add(b)
        out.setdefault(b, set())
    return out


class LoopTests(unittest.TestCase):
    def test_no_loop_in_a_chain(self):
        self.assertEqual(find_loops(["a", "b", "c"], succ(("a", "b"), ("b", "c"))), [])

    def test_two_node_loop(self):
        self.assertEqual(find_loops(["a", "b"], succ(("a", "b"), ("b", "a"))), [["a", "b"]])

    def test_self_loop(self):
        self.assertEqual(find_loops(["a"], succ(("a", "a"))), [["a"]])

    def test_nodes_downstream_of_a_loop_are_not_in_it(self):
        s = succ(("n", "a"), ("a", "m"), ("m", "a"), ("m", "d"))
        self.assertEqual(find_loops(["n", "a", "m", "d"], s), [["a", "m"]])

    def test_two_separate_loops(self):
        s = succ(("a", "b"), ("b", "a"), ("c", "d"), ("d", "c"))
        self.assertEqual(sorted(find_loops(["a", "b", "c", "d"], s)), [["a", "b"], ["c", "d"]])

    def test_long_chain_does_not_overflow_the_stack(self):
        ids = [f"n{i}" for i in range(5000)]
        s = succ(*[(ids[i], ids[i + 1]) for i in range(4999)], (ids[-1], ids[0]))
        self.assertEqual(len(find_loops(ids, s)[0]), 5000)


class OrderTests(unittest.TestCase):
    def test_topological_order(self):
        order = topological_order(["c", "b", "a"], succ(("a", "b"), ("b", "c")))
        self.assertEqual(order, ["a", "b", "c"])

    def test_cycle_members_are_left_out(self):
        order = topological_order(["n", "a", "b"], succ(("n", "a"), ("a", "b"), ("b", "a")))
        self.assertEqual(order, ["n"])

    def test_downstream(self):
        self.assertEqual(downstream("a", succ(("a", "b"), ("b", "c"), ("x", "c"))), ["b", "c"])


if __name__ == "__main__":
    unittest.main()
