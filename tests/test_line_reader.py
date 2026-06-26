"""Tests for the line reader (completion helpers and test-only edit loop)."""

import io
import unittest
import unittest.mock

from pyshell.line_reader import (
    IterableKeySource,
    apply_completion,
    read_editable_line,
    word_at_cursor,
)


class TestWordAtCursor(unittest.TestCase):
    def test_middle_of_word(self):
        self.assertEqual(word_at_cursor("hello world", 8), ("wo", 6))

    def test_pipe_starts_new_word(self):
        self.assertEqual(word_at_cursor("cat f |for", 7), ("", 7))
        self.assertEqual(word_at_cursor("cat f |for", 8), ("f", 7))


class TestApplyCompletion(unittest.TestCase):
    def test_replaces_word_and_adds_space(self):
        line, pos = apply_completion("pw", 2, "pwd")
        self.assertEqual(line, "pwd ")
        self.assertEqual(pos, 4)


class TestReadEditableLine(unittest.TestCase):
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

    def test_test_key_source_loop(self):
        result = read_editable_line(
            ">>> ",
            history=[],
            complete=lambda _l, _p: [],
            key_source=IterableKeySource(list("hi") + ["ENTER"]),
        )
        self.assertEqual(result, "hi")

    def test_tab_single_completion_via_test_loop(self):
        def complete(line, pos):
            word, _ = word_at_cursor(line, pos)
            if word == "pw":
                return ["pwd"]
            return []

        result = read_editable_line(
            ">>> ",
            history=[],
            complete=complete,
            key_source=IterableKeySource(list("pw") + ["TAB", "ENTER"]),
        )
        self.assertEqual(result, "pwd ")


class TestPromptToolkitIntegration(unittest.TestCase):
    def test_prompt_toolkit_reads_line(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=True):
            with unittest.mock.patch("prompt_toolkit.PromptSession") as mock_cls:
                mock_cls.return_value.prompt.return_value = "hello"
                result = read_editable_line(
                    ">>> ",
                    history=[],
                    complete=lambda _l, _p: [],
                )
        self.assertEqual(result, "hello")
        mock_cls.return_value.prompt.assert_called_once()
