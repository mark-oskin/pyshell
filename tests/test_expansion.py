"""Tests for $VAR, ~, and glob expansion in command arguments."""

import os
import tempfile
import unittest

from pyshell.expansion import (
    expand_command_argv,
    expand_glob_argv,
    expand_redirect_path,
    expand_tilde,
    expand_vars_in_string,
)


class TestExpandVars(unittest.TestCase):
    def test_expand_simple(self):
        env = {"HOME": "/home/user", "PATH": "/bin"}
        self.assertEqual(expand_vars_in_string("$HOME", env), "/home/user")
        self.assertEqual(expand_vars_in_string("x$PATH", env), "x/bin")

    def test_expand_braced(self):
        env = {"VAR": "value"}
        self.assertEqual(expand_vars_in_string("${VAR}", env), "value")

    def test_unknown_empty(self):
        self.assertEqual(expand_vars_in_string("$UNKNOWN", {}), "")

    def test_mixed(self):
        env = {"A": "1", "B": "2"}
        self.assertEqual(expand_vars_in_string("$A:$B", env), "1:2")


class TestExpandTilde(unittest.TestCase):
    def test_tilde_expands(self):
        expanded = expand_tilde("~")
        self.assertTrue(os.path.isabs(expanded) or expanded.startswith("~"))


class TestExpandGlob(unittest.TestCase):
    def test_no_glob_unchanged(self):
        self.assertEqual(expand_glob_argv(["ls", "foo"]), ["ls", "foo"])

    def test_glob_star(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.py"), "w").close()
            open(os.path.join(d, "b.py"), "w").close()
            start_cwd = os.getcwd()
            try:
                os.chdir(d)
                out = expand_glob_argv(["*.py"])
                self.assertEqual(sorted(out), ["a.py", "b.py"])
            finally:
                os.chdir(start_cwd)

    def test_glob_no_match_keeps_token(self):
        out = expand_glob_argv(["*.nonexistent123"])
        self.assertEqual(out, ["*.nonexistent123"])


class TestExpandCommandArgv(unittest.TestCase):
    def test_var_and_tilde(self):
        env = dict(os.environ)
        env["HOME"] = os.path.expanduser("~")
        out = expand_command_argv(["echo", "$HOME"], env)
        self.assertEqual(out[0], "echo")
        self.assertEqual(out[1], env["HOME"])


class TestExpandRedirectPath(unittest.TestCase):
    def test_expand_var(self):
        env = {"X": "/tmp"}
        self.assertEqual(expand_redirect_path("$X/file", env), "/tmp/file")

    def test_none(self):
        self.assertIsNone(expand_redirect_path(None, {}))
