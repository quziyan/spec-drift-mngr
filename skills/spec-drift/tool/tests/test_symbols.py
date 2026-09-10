"""Tests for symbols.py."""
from __future__ import annotations

import unittest

import symbols as S


class TestCommentAbsorption(unittest.TestCase):
    """Absorbing preceding comments upward, including the file-header exception and the blank-line priority."""

    def test_absorbs_adjacent_comment_block(self):
        src = "X = 1\n\n# c1\n# c2\ndef f():\n    return 1\n"
        _top, syms = S.parse_symbols(src)
        self.assertEqual(syms["f"], [(3, 6)])

    def test_file_header_comments_not_absorbed(self):
        """If the comment run reaches line 1 of the file without meeting a blank or non-comment line, it counts as a file header and none of it is absorbed."""
        src = "# header A\n# header B\ndef f():\n    return 1\n"
        _top, syms = S.parse_symbols(src)
        self.assertEqual(syms["f"], [(3, 4)])

    def test_leading_blank_line_defeats_header_exception(self):
        """When the file opens with a blank line the scan stops there, the file-header exception does not fire, and absorption happens as usual."""
        src = "\n# c1\n# c2\ndef f():\n    return 1\n"
        _top, syms = S.parse_symbols(src)
        self.assertEqual(syms["f"], [(2, 5)])

    def test_blank_line_stops_absorption(self):
        src = "# head\n\n# attached\ndef f():\n    return 1\n"
        _top, syms = S.parse_symbols(src)
        self.assertEqual(syms["f"], [(3, 5)])

    def test_decorator_included(self):
        src = "# c\n@deco\ndef f():\n    return 1\n"
        _top, syms = S.parse_symbols(src)
        # File-header exception: the comment run reaches line 1, so nothing is absorbed;
        # the span starts at the decorator on line 2.
        self.assertEqual(syms["f"], [(2, 4)])


class TestFiveKinds(unittest.TestCase):
    """The five kinds of symbol."""

    SRC = (
        "import os\n"                     # 1
        "\n"                              # 2
        "MAX = 3\n"                       # 3
        "NAME: str = 'x'\n"               # 4
        "A, B = 1, 2\n"                   # 5  tuple unpacking: creates no symbol
        "\n"                              # 6
        "\n"                              # 7
        "def top():\n"                    # 8
        "    return MAX\n"                # 9
        "\n"                              # 10
        "\n"                              # 11
        "class Foo:\n"                    # 12
        "    def bar(self):\n"            # 13
        "        return 1\n"              # 14
        "\n"                              # 15
        "\n"                              # 16
        "async def coro():\n"             # 17
        "    return None\n"               # 18
    )

    def test_all_kinds_located(self):
        top, syms = S.parse_symbols(self.SRC)
        self.assertEqual(syms["MAX"], [(3, 3)])
        self.assertEqual(syms["NAME"], [(4, 4)])
        self.assertEqual(syms["top"], [(8, 9)])
        self.assertEqual(syms["Foo"], [(12, 14)])
        self.assertEqual(syms["Foo::bar"], [(13, 14)])
        self.assertEqual(syms["coro"], [(17, 18)])

    def test_tuple_unpacking_makes_no_symbol(self):
        """A module-level assignment that unpacks a tuple creates no constant symbol; its lines fall into ::<module>."""
        _top, syms = S.parse_symbols(self.SRC)
        self.assertNotIn("A", syms)
        self.assertNotIn("B", syms)

    def test_top_level_excludes_methods(self):
        """Top-level symbols feed the ::<module> projection; class methods sit inside the class's span and are not listed separately."""
        top, _syms = S.parse_symbols(self.SRC)
        names = [n for (n, _s, _e) in top]
        self.assertEqual(names, ["MAX", "NAME", "top", "Foo", "coro"])


class TestDuplicateNames(unittest.TestCase):
    """A name defined more than once -> the ordered set of all candidate spans, with the fingerprint concatenating them in order of appearance."""

    SRC = (
        "if COND:\n"                      # 1
        "    pass\n"                      # 2
        "\n"                              # 3
        "def f():\n"                      # 4
        "    return 1\n"                  # 5
        "\n"                              # 6
        "\n"                              # 7
        "def f():\n"                      # 8
        "    return 2\n"                  # 9
    )

    def test_keeps_all_candidates_in_order(self):
        _top, syms = S.parse_symbols(self.SRC)
        self.assertEqual(syms["f"], [(4, 5), (8, 9)])

    def test_fingerprint_covers_all_candidates(self):
        """Editing the first definition must move the fingerprint too — taking only the last candidate was the mistake in earlier versions."""
        lines = S.split_lines(self.SRC)
        before = S.fingerprint(lines, [(4, 5), (8, 9)])
        mutated = self.SRC.replace("return 1", "return 99")
        mlines = S.split_lines(mutated)
        _t, msyms = S.parse_symbols(mutated)
        after = S.fingerprint(mlines, msyms["f"])
        self.assertNotEqual(before, after)


class TestNormalization(unittest.TestCase):
    """Unify line endings, then strip trailing whitespace from every line."""

    def test_trailing_whitespace_ignored(self):
        a = "def f():\n    return 1\n"
        b = "def f():   \n    return 1\t\n"
        fa = S.fingerprint(S.split_lines(a), S.parse_symbols(a)[1]["f"])
        fb = S.fingerprint(S.split_lines(b), S.parse_symbols(b)[1]["f"])
        self.assertEqual(fa, fb)

    def test_crlf_equals_lf(self):
        a = "def f():\n    return 1\n"
        b = "def f():\r\n    return 1\r\n"
        fa = S.fingerprint(S.split_lines(a), S.parse_symbols(a)[1]["f"])
        fb = S.fingerprint(S.split_lines(b), S.parse_symbols(b)[1]["f"])
        self.assertEqual(fa, fb)

    def test_fingerprint_prefixed(self):
        a = "def f():\n    return 1\n"
        self.assertTrue(
            S.fingerprint(S.split_lines(a), S.parse_symbols(a)[1]["f"]).startswith("sha256:")
        )


class TestModulePlaceholder(unittest.TestCase):
    """The ::<module> pseudo-symbol: a projection built from anonymous placeholders."""

    SRC = (
        "import os\n"                     # 1
        "\n"                              # 2
        "def a():\n"                      # 3
        "    return 1\n"                  # 4
        "\n"                              # 5
        "\n"                              # 6
        "def b():\n"                      # 7
        "    return 2\n"                  # 8
    )

    def _mod_fp(self, src):
        top, _ = S.parse_symbols(src)
        return S.module_fingerprint(S.split_lines(src), top)

    def test_renaming_a_function_does_not_move_module(self):
        """The placeholder is anonymous, so a rename does not pull ::<module> into the changed set."""
        renamed = self.SRC.replace("def a()", "def a_renamed()")
        self.assertEqual(self._mod_fp(self.SRC), self._mod_fp(renamed))

    def test_swapping_two_functions_does_not_move_module(self):
        swapped = (
            "import os\n\n"
            "def b():\n    return 2\n\n\n"
            "def a():\n    return 1\n"
        )
        self.assertEqual(self._mod_fp(self.SRC), self._mod_fp(swapped))

    def test_import_moved_across_functions_does_move_module(self):
        """Position is signal: an import moved across functions must be caught."""
        moved = (
            "\n"
            "def a():\n    return 1\n"
            "\n"
            "import os\n"
            "\n"
            "def b():\n    return 2\n"
        )
        self.assertNotEqual(self._mod_fp(self.SRC), self._mod_fp(moved))

    def test_editing_function_body_does_not_move_module(self):
        edited = self.SRC.replace("return 1", "return 111")
        self.assertEqual(self._mod_fp(self.SRC), self._mod_fp(edited))


if __name__ == "__main__":
    unittest.main()
