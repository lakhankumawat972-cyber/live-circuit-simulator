import unittest

from app.formula import FormulaError, compile_formula


def spice(text):
    return compile_formula(text).to_spice(lambda name: f"net_{name}")


class FormulaTests(unittest.TestCase):
    def test_regenerates_from_ast_with_full_brackets(self):
        self.assertEqual(spice("a * 2 + b"), "((V(net_a)*2.0)+V(net_b))")
        self.assertEqual(spice("-(a+1)/2"), "((0-(V(net_a)+1.0))/2.0)")

    def test_evaluates_with_precedence(self):
        self.assertEqual(compile_formula("a * 2 + b").evaluate({"a": 3, "b": 4}), 10)
        self.assertEqual(compile_formula("(a + b) * 2").evaluate({"a": 3, "b": 4}), 14)
        self.assertEqual(compile_formula("a - -b").evaluate({"a": 1, "b": 2}), 3)

    def test_reports_variables_used(self):
        self.assertEqual(compile_formula("2*b").variables, ("b",))
        self.assertEqual(compile_formula("b+a").variables, ("a", "b"))

    def test_division_by_zero_raises(self):
        with self.assertRaises(ZeroDivisionError):
            compile_formula("a / (b - b)").evaluate({"a": 1, "b": 1})

    def test_rejects_injection_and_everything_else(self):
        bad = [
            "a + b\n.control\nshell ls",
            "a + b\r\n.end",
            "a+b; shell ls",
            "a ** 2",
            "a^2",
            "sin(a)",
            "A + b",
            "c + 1",
            "1e5 + a",
            "0x10",
            "a $ b",
            "a + b # c",
            "a + b",
            "a + ١",  # arabic-indic digit one
            "",
            "   ",
            "a +",
            "(a + b",
            "a + b)",
            "a b",
            "1.2.3",
            ".",
            "a" * 201,
            "(" * 100 + "a" + ")" * 100,
            "1" * 400,
        ]
        for text in bad:
            with self.subTest(text=text[:30]):
                with self.assertRaises(FormulaError):
                    compile_formula(text)

    def test_non_text_rejected(self):
        with self.assertRaises(FormulaError):
            compile_formula(None)

    def test_message_names_the_offending_character(self):
        with self.assertRaises(FormulaError) as ctx:
            compile_formula("a\n.control")
        self.assertIn("new line", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
