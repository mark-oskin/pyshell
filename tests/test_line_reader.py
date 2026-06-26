"""Tests for the built-in line editor."""

import io
import unittest
import unittest.mock

from pyshell.line_reader import (
    IterableKeySource,
    apply_completion,
    read_editable_line,
    redraw_line,
    word_at_cursor,
    _history_edit_line,
    _tty_nl,
)


class TestWordAtCursor(unittest.TestCase):
    def test_middle_of_word(self):
        self.assertEqual(word_at_cursor("hello world", 8), ("wo", 6))

    def test_end_of_line(self):
        self.assertEqual(word_at_cursor("cat file", 8), ("file", 4))

    def test_empty_line(self):
        self.assertEqual(word_at_cursor("", 0), ("", 0))

    def test_pipe_starts_new_word(self):
        self.assertEqual(word_at_cursor("cat f |for", 7), ("", 7))
        self.assertEqual(word_at_cursor("cat f |for", 8), ("f", 7))
        self.assertEqual(word_at_cursor("cat f |for", 10), ("for", 7))


class TestApplyCompletion(unittest.TestCase):
    def test_replaces_word_and_adds_space(self):
        line, pos = apply_completion("pw", 2, "pwd")
        self.assertEqual(line, "pwd ")
        self.assertEqual(pos, 4)

    def test_dir_completion_keeps_trailing_sep(self):
        line, pos = apply_completion("cd sr", 5, "src/")
        self.assertEqual(line, "cd src/")
        self.assertEqual(pos, 7)


class TestHistoryEditLine(unittest.TestCase):
    def test_flattens_multiline(self):
        entry = "cat README.md |for f in sys.stdin:\n    print(f)"
        self.assertEqual(
            _history_edit_line(entry),
            "cat README.md |for f in sys.stdin: print(f)",
        )


class TestReadEditableLine(unittest.TestCase):
    def _read(self, prompt: str, keys: list[str], *, history: list[str] | None = None) -> str | None:
        out = io.StringIO()
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = read_editable_line(
                prompt,
                history=history or [],
                complete=lambda _line, _pos: [],
                key_source=IterableKeySource(keys),
            )
            output = mock_out.getvalue()
        return result, output

    def test_types_and_enters(self):
        result, output = self._read(">>> ", list("hello") + ["ENTER"])
        self.assertEqual(result, "hello")
        self.assertIn(">>> hello", output)

    def test_backspace(self):
        result, _ = self._read(">>> ", list("ab") + ["BACKSPACE", "c", "ENTER"])
        self.assertEqual(result, "ac")

    def test_left_right_insert(self):
        result, _ = self._read(">>> ", list("ab") + ["LEFT", "x", "ENTER"])
        self.assertEqual(result, "axb")

    def test_history_up_down(self):
        result, _ = self._read(
            ">>> ",
            ["UP", "DOWN", "ENTER"],
            history=["first", "second"],
        )
        self.assertEqual(result, "")

    def test_history_up_flattens_multiline(self):
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            read_editable_line(
                ">>> ",
                history=["cat f |for x in y:\n    print(x)"],
                complete=lambda _l, _p: [],
                key_source=IterableKeySource(["UP", "ENTER"]),
            )
        self.assertIn("cat f |for x in y: print(x)", out.getvalue())
        self.assertNotIn("\n    print", out.getvalue())

    def test_tab_single_completion(self):
        def complete(line, pos):
            word, _ = word_at_cursor(line, pos)
            if word == "pw":
                return ["pwd"]
            return []

        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO):
            result = read_editable_line(
                ">>> ",
                history=[],
                complete=complete,
                key_source=IterableKeySource(list("pw") + ["TAB", "ENTER"]),
            )
        self.assertEqual(result, "pwd ")

    def test_ctrl_c_raises(self):
        with self.assertRaises(KeyboardInterrupt):
            with unittest.mock.patch("sys.stdout", new_callable=io.StringIO):
                read_editable_line(
                    ">>> ",
                    history=[],
                    complete=lambda _l, _p: [],
                    key_source=IterableKeySource(["CTRL_C"]),
                )

    def test_non_tty_uses_stdin_readline(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=False):
            with unittest.mock.patch("sys.stdin.readline", return_value="pipe line\n"):
                with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                    result = read_editable_line(
                        ">>> ",
                        history=[],
                        complete=lambda _l, _p: [],
                    )
        self.assertEqual(result, "pipe line")
        self.assertEqual(out.getvalue(), ">>> ")

    def test_prompt_with_spaces_written_in_full(self):
        prompt = "[Local Settings] >>> "
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            read_editable_line(
                prompt,
                history=[],
                complete=lambda _l, _p: [],
                key_source=IterableKeySource(["ENTER"]),
            )
        self.assertIn(prompt, out.getvalue())


class TestRedrawLine(unittest.TestCase):
    def test_redraw_with_cursor_not_at_end(self):
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            redraw_line(">>> ", "abcd", 2)
        self.assertIn(">>> abcd", out.getvalue())

    def test_enter_uses_crlf(self):
        self.assertEqual(_tty_nl(), "\r\n")
