"""Tests for command name resolution (.py scripts on PATH)."""

import os
import stat
import sys
import tempfile
import unittest
import unittest.mock

from pyshell.command_resolve import (
    lookup_command,
    path_lookup_names,
    resolve_command_argv,
)


class TestPathLookupNames(unittest.TestCase):
    def test_plain_name_adds_py(self):
        self.assertEqual(path_lookup_names("program"), ["program", "program.py"])

    def test_trailing_dot(self):
        self.assertEqual(path_lookup_names("program."), ["program.py"])

    def test_existing_extension_unchanged(self):
        self.assertEqual(path_lookup_names("foo.py"), ["foo.py"])
        self.assertEqual(path_lookup_names("foo.sh"), ["foo.sh"])


class TestResolveCommandArgv(unittest.TestCase):
    def _with_path(self, *dirs: str) -> str:
        return os.pathsep.join(dirs)

    def test_falls_back_to_py_on_path(self):
        with tempfile.TemporaryDirectory() as bindir:
            script = os.path.join(bindir, "program.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print('ok')\n")
            path_env = self._with_path(bindir)
            resolved = resolve_command_argv(["program"], path_env=path_env)
            self.assertEqual(resolved, [sys.executable, script])

    def test_prefers_executable_over_py(self):
        with tempfile.TemporaryDirectory() as bindir:
            exe = os.path.join(bindir, "program")
            script = os.path.join(bindir, "program.py")
            open(exe, "w").close()
            open(script, "w").close()
            os.chmod(exe, stat.S_IRWXU)
            path_env = self._with_path(bindir)
            resolved = resolve_command_argv(["program"], path_env=path_env)
            self.assertEqual(resolved, [exe])

    def test_trailing_dot_resolves_py(self):
        with tempfile.TemporaryDirectory() as bindir:
            script = os.path.join(bindir, "program.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print('ok')\n")
            path_env = self._with_path(bindir)
            resolved = resolve_command_argv(["program."], path_env=path_env)
            self.assertEqual(resolved, [sys.executable, script])

    def test_path_qualified_dot(self):
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "agent.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write("print('ok')\n")
            rel = os.path.join(".", "agent.")
            cwd = os.getcwd()
            try:
                os.chdir(d)
                resolved = resolve_command_argv([rel])
                self.assertEqual(resolved[0], sys.executable)
                self.assertTrue(os.path.samefile(resolved[1], script))
            finally:
                os.chdir(cwd)

    def test_not_found(self):
        with tempfile.TemporaryDirectory() as bindir:
            resolved = resolve_command_argv(
                ["missing"],
                path_env=self._with_path(bindir),
            )
            self.assertIsNone(resolved)

    def test_lookup_command_returns_script_path(self):
        with tempfile.TemporaryDirectory() as bindir:
            script = os.path.join(bindir, "program.py")
            open(script, "w").close()
            path_env = self._with_path(bindir)
            self.assertEqual(lookup_command("program", path_env=path_env), script)
