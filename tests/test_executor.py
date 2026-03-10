"""Tests for pyshell executor: Python eval and command execution."""

import os
import sys
import tempfile
import unittest

from pyshell.executor import Executor
from pyshell.builtins import run_builtin_command


class TestRunPython(unittest.TestCase):
    """run_python executes Python and returns expression values."""

    def test_expression_result(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        result = ex.run_python("2+3", "2+3")
        self.assertEqual(result, 5)

    def test_assignment_no_return(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        result = ex.run_python("x = 10", "x = 10")
        self.assertIsNone(result)
        ns = ex._get_namespace()
        self.assertEqual(ns["x"], 10)

    def test_env_vars_in_namespace(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_python("1", "1")
        ns = ex._get_namespace()
        self.assertIn("PATH", ns)
        self.assertEqual(ns["PATH"], os.environ.get("PATH", ""))

    def test_last_exit_code_in_namespace(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.set_history_callback(lambda: [])
        ns = ex._get_namespace()
        self.assertIn("last_exit_code", ns)
        self.assertEqual(ns["last_exit_code"], 0)


class TestRunBuiltinCommand(unittest.TestCase):
    """run_builtin_command runs builtins by name."""

    def test_pwd_returns_cwd(self):
        result = run_builtin_command("pwd", [])
        self.assertEqual(result, os.getcwd())

    def test_cd_changes_dir(self):
        start = os.getcwd()
        tmpdir = tempfile.gettempdir()
        try:
            run_builtin_command("cd", [tmpdir])
            self.assertEqual(os.getcwd(), tmpdir)
        finally:
            os.chdir(start)

    def test_unknown_is_none(self):
        result = run_builtin_command("nonexistent_builtin_xyz", [])
        self.assertIsNone(result)


class TestRunCommand(unittest.TestCase):
    """Executor.run_command runs builtins or external commands."""

    def test_pwd_via_run_command(self):
        ex = Executor()
        result = ex.run_command(["pwd"])
        self.assertEqual(result, os.getcwd())

    def test_nonexistent_command_exits_127(self):
        ex = Executor()
        with self.assertRaises(SystemExit) as ctx:
            ex.run_command(["this_command_does_not_exist_xyz"])
        self.assertEqual(ctx.exception.code, 127)

    def test_run_command_with_redirect(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            ex.run_command(
                [sys.executable, "-c", "print('hello')"],
                redirects=[(">", path)],
            )
            with open(path, encoding="utf-8") as f2:
                self.assertEqual(f2.read().strip(), "hello")
        finally:
            os.unlink(path)

    def test_run_command_expands_var(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            ex.run_command(
                [sys.executable, "-c", "import sys; print(sys.argv[1])", "$PATH"],
                redirects=[(">", path)],
            )
            with open(path, encoding="utf-8") as f2:
                self.assertEqual(f2.read().strip(), os.environ.get("PATH", ""))
        finally:
            os.unlink(path)

    def test_set_prompt(self):
        ex = Executor()
        ex.set_prompt("{base} $ ")
        p = ex.get_prompt()
        self.assertIn("$", p)
        self.assertNotIn("{base}", p)
        ex.set_prompt(None)
        self.assertIn(">>>", ex.get_prompt())

    def test_alias_command_sets_and_lists(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_command(["alias", "ll=ls -la"])
        self.assertIn("ll", ex._aliases)
        self.assertEqual(ex._aliases["ll"], "ls -la")
        ex.run_command(["unalias", "ll"])
        self.assertNotIn("ll", ex._aliases)

    def test_last_exit_code_after_command(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_command(["pwd"])
        self.assertEqual(ex._last_exit_code, 0)
        ns = ex._get_namespace()
        self.assertEqual(ns["last_exit_code"], 0)


class TestRunPipeline(unittest.TestCase):
    """Executor.run_pipeline runs cmd1 | cmd2 | ..."""

    def test_pipeline_single_is_run_as_command(self):
        ex = Executor()
        result = ex.run_pipeline([["pwd"]])
        self.assertEqual(result, os.getcwd())

    def test_pipeline_two_stages(self):
        """pwd | consumer: pwd output is piped to a command that reads stdin."""
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        # Use python to consume stdin (cross-platform; cat may not exist on Windows)
        result = ex.run_pipeline([
            ["pwd"],
            [sys.executable, "-c", "import sys; sys.stdin.read(); sys.exit(0)"],
        ])
        self.assertIsNone(result)
        self.assertEqual(ex._last_exit_code, 0)

    def test_pipeline_sets_last_exit_code(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_pipeline([["pwd"], [sys.executable, "-c", "import sys; sys.stdin.read(); sys.exit(0)"]])
        self.assertEqual(ex._last_exit_code, 0)


class TestBackgroundJobs(unittest.TestCase):
    def test_jobs_initially_empty(self):
        ex = Executor()
        self.assertEqual(ex._jobs, [])

    def test_background_command_adds_job(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_command([sys.executable, "-c", "import time; time.sleep(0.05)"], background=True)
        self.assertEqual(len(ex._jobs), 1)
        self.assertIn("id", ex._jobs[0])
        self.assertIn("procs", ex._jobs[0])
        ex._jobs[0]["procs"][0].wait()
        ex._jobs.clear()


class TestTypeWhich(unittest.TestCase):
    """type and which builtins."""

    def test_type_builtin(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            ex.run_command(["type", "pwd"])
        self.assertIn("pwd is a shell builtin", out.getvalue())

    def test_type_alias(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.set_alias("ll", "ls -la")
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            ex.run_command(["type", "ll"])
        self.assertIn("ll is aliased to", out.getvalue())

    def test_which_builtin(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            ex.run_command(["which", "cd"])
        self.assertIn("cd", out.getvalue())
        self.assertIn("builtin", out.getvalue())


class TestDirectoryStack(unittest.TestCase):
    """pushd, popd, dirs."""

    def test_pushd_popd_dirs(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        start = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            try:
                ex.run_command(["pushd", d])
                self.assertEqual(os.getcwd(), d)
                self.assertEqual(len(ex._dir_stack), 1)
                self.assertEqual(ex._dir_stack[0], start)
                result = ex.run_command(["dirs"])
                self.assertIn(d, result)
                self.assertIn(start, result)
                ex.run_command(["popd"])
                self.assertEqual(os.getcwd(), start)
                self.assertEqual(len(ex._dir_stack), 0)
            finally:
                if os.getcwd() != start:
                    os.chdir(start)


class TestPipelineRedirects(unittest.TestCase):
    """Redirects applied to pipelines (stdin to first, stdout/stderr from last)."""

    def test_pipeline_stdout_redirect(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            path = f.name
        try:
            # print hello | copy stdin to stdout, redirect to file
            ex.run_pipeline(
                [
                    [sys.executable, "-c", "print('hello')"],
                    [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                ],
                redirects=[(">", path)],
            )
            with open(path, encoding="utf-8") as r:
                self.assertEqual(r.read().strip(), "hello")
        finally:
            os.unlink(path)
