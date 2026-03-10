"""Tests for pyshell parser: Python vs command classification, pipelines, redirects."""

import unittest
from pyshell.parser import (
    parse_line,
    parse_redirects,
    has_conditional,
    split_conditional,
    _split_command,
    _split_pipeline,
)


class TestParseLine(unittest.TestCase):
    """parse_line(line) -> ('python'|'command', payload)."""

    def test_single_identifier_is_command(self):
        """Single words like ls, pwd must be run as commands, not Python."""
        kind, payload = parse_line("ls")
        self.assertEqual(kind, "command")
        self.assertEqual(payload, ["ls"])

        kind, payload = parse_line("pwd")
        self.assertEqual(kind, "command")
        self.assertEqual(payload, ["pwd"])

        kind, payload = parse_line("  pwd  ")
        self.assertEqual(kind, "command")
        self.assertEqual(payload, ["pwd"])

    def test_expression_is_python(self):
        kind, payload = parse_line("2+3")
        self.assertEqual(kind, "python")
        self.assertEqual(payload, "2+3")

        kind, payload = parse_line("2 + 3")
        self.assertEqual(kind, "python")
        self.assertEqual(payload, "2 + 3")

    def test_assignment_is_python(self):
        kind, payload = parse_line("x = 1")
        self.assertEqual(kind, "python")
        self.assertIn("x", payload)
        self.assertIn("=", payload)

    def test_function_call_is_python(self):
        kind, payload = parse_line("print(1)")
        self.assertEqual(kind, "python")

    def test_command_with_args_is_command(self):
        kind, payload = parse_line("ls -la")
        self.assertEqual(kind, "command")
        self.assertEqual(payload, ["ls", "-la"])

    def test_empty_returns_python(self):
        kind, payload = parse_line("")
        self.assertEqual(kind, "python")
        self.assertEqual(payload, "")

    def test_pipeline_two_commands(self):
        kind, payload = parse_line("ls | grep py")
        self.assertEqual(kind, "pipeline")
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0], ["ls"])
        self.assertEqual(payload[1], ["grep", "py"])

    def test_pipeline_three_commands(self):
        kind, payload = parse_line("echo a | cat | cat")
        self.assertEqual(kind, "pipeline")
        self.assertEqual(len(payload), 3)
        self.assertEqual(payload[0], ["echo", "a"])
        self.assertEqual(payload[1], ["cat"])
        self.assertEqual(payload[2], ["cat"])

    def test_pipeline_no_spaces_around_pipe(self):
        """ls|wc (no spaces) must be pipeline, not Python (which would treat | as bitwise or)."""
        kind, payload = parse_line("ls|wc")
        self.assertEqual(kind, "pipeline")
        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0], ["ls"])
        self.assertEqual(payload[1], ["wc"])

    def test_pipe_inside_quotes_not_split(self):
        # "a|b" is one token; single identifier "a|b" isn't valid, so falls through
        # Line with = or ( is Python. Here we have no = or (, and "a|b".split() is one part
        # So _is_single_identifier('echo "a|b"') - split gives ['echo', '"a|b"'] - len 2, so False
        # Then "=" not in line, "(" not in line, parts[0].isidentifier() -> "echo".isidentifier() True
        # So we'd return as_command(). And as_command checks "|" in line_stripped - yes
        # _pipe_not_inside_quotes('echo "a|b"') - we see ", set quote, then a|b, then "
        # So when we see | we're inside quote, we don't return True. So we return False.
        # So we don't split pipeline. So we return ("command", _split_command(line))
        # So payload is ["echo", "a|b"] (the quotes are stripped by _split_command)
        kind, payload = parse_line('echo "a|b"')
        self.assertEqual(kind, "command")
        self.assertEqual(payload, ["echo", "a|b"])


class TestSplitCommand(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(_split_command("ls -la"), ["ls", "-la"])

    def test_quotes(self):
        self.assertEqual(_split_command('echo "hello world"'), ["echo", "hello world"])
        self.assertEqual(_split_command("echo 'hi'"), ["echo", "hi"])


class TestSplitPipeline(unittest.TestCase):
    def test_two_segments(self):
        self.assertEqual(_split_pipeline("ls | grep x"), ["ls", "grep x"])

    def test_three_segments(self):
        self.assertEqual(_split_pipeline("a | b | c"), ["a", "b", "c"])


class TestParseRedirects(unittest.TestCase):
    def test_no_redirects(self):
        argv, redirects, bg = parse_redirects("echo hi")
        self.assertEqual(argv, ["echo", "hi"])
        self.assertEqual(redirects, [])
        self.assertFalse(bg)

    def test_stdout_redirect(self):
        argv, redirects, bg = parse_redirects("echo hi > out.txt")
        self.assertEqual(argv, ["echo", "hi"])
        self.assertEqual(redirects, [(">", "out.txt")])
        self.assertFalse(bg)

    def test_append_redirect(self):
        argv, redirects, _ = parse_redirects("echo x >> log.txt")
        self.assertEqual(argv, ["echo", "x"])
        self.assertEqual(redirects, [(">>", "log.txt")])

    def test_stdin_redirect(self):
        argv, redirects, _ = parse_redirects("cat < input.txt")
        self.assertEqual(argv, ["cat"])
        self.assertEqual(redirects, [("<", "input.txt")])

    def test_background(self):
        argv, redirects, bg = parse_redirects("sleep 1 &")
        self.assertEqual(argv, ["sleep", "1"])
        self.assertEqual(redirects, [])
        self.assertTrue(bg)

    def test_redirect_and_background(self):
        argv, redirects, bg = parse_redirects("echo hi > f.txt &")
        self.assertEqual(argv, ["echo", "hi"])
        self.assertEqual(redirects, [(">", "f.txt")])
        self.assertTrue(bg)


class TestConditional(unittest.TestCase):
    """has_conditional and split_conditional for && and ||."""

    def test_has_conditional_true(self):
        self.assertTrue(has_conditional("echo a && echo b"))
        self.assertTrue(has_conditional("false || echo ok"))

    def test_has_conditional_false(self):
        self.assertFalse(has_conditional("echo a"))
        self.assertFalse(has_conditional('echo "a && b"'))

    def test_split_conditional_two_and(self):
        segments = split_conditional("echo a && echo b")
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], ("echo a", "&&"))
        self.assertEqual(segments[1], ("echo b", None))

    def test_split_conditional_or(self):
        segments = split_conditional("false || echo ok")
        self.assertEqual(segments[0], ("false", "||"))
        self.assertEqual(segments[1], ("echo ok", None))
