"""Tests for pyshell executor: Python eval and command execution."""

import io
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

from pyshell.executor import Executor, _job_control_available
from pyshell.builtins import run_builtin_command, run_ls_dir


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

    def test_cd_with_space_in_path(self):
        """cd works when path has a space (args passed as separate tokens)."""
        start = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="pyshell test ") as tmpdir:
            try:
                run_builtin_command("cd", tmpdir.split())
                self.assertEqual(os.getcwd(), tmpdir)
            finally:
                os.chdir(start)

    def test_unknown_is_none(self):
        result = run_builtin_command("nonexistent_builtin_xyz", [])
        self.assertIsNone(result)

    def test_ls_with_space_in_path(self):
        """ls works when path has a space and is passed as separate tokens (e.g. unquoted 'ls My Folder')."""
        start = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="pyshell test ") as parent:
            try:
                os.chdir(parent)
                dir_with_space = os.path.join(parent, "My Folder")
                os.mkdir(dir_with_space)
                with open(os.path.join(dir_with_space, "file.txt"), "w") as f:
                    f.write("x")
                # Simulate argv when user types "ls My Folder" (no quotes) -> two tokens
                out = run_ls_dir(["ls", "My", "Folder"])
                self.assertIn("file.txt", out)
                self.assertNotIn("No such file", out)
            finally:
                os.chdir(start)


class TestRunCommand(unittest.TestCase):
    """Executor.run_command runs builtins or external commands."""

    def test_pwd_via_run_command(self):
        ex = Executor()
        result = ex.run_command(["pwd"])
        self.assertEqual(result, os.getcwd())

    @unittest.skipUnless(os.name == "nt", "ls/dir builtin only on Windows")
    def test_ls_dir_with_space_in_path_via_run_command(self):
        """On Windows, 'ls My Folder' (two tokens) lists directory 'My Folder' when it exists."""
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        start = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="pyshell test ") as parent:
            try:
                os.chdir(parent)
                dir_with_space = os.path.join(parent, "My Folder")
                os.mkdir(dir_with_space)
                with open(os.path.join(dir_with_space, "a.txt"), "w") as f:
                    f.write("a")
                result = ex.run_command(["ls", "My", "Folder"])
                self.assertIn("a.txt", result or "")
                self.assertEqual(ex._last_exit_code, 0)
            finally:
                os.chdir(start)

    def test_nonexistent_command_exits_127(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        result = ex.run_command(["this_command_does_not_exist_xyz"])
        self.assertIsNone(result)
        self.assertEqual(ex._last_exit_code, 127)

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

    def test_prompt_with_cwd_containing_space(self):
        """Prompt shows full directory name when cwd has a space (space-like char in path)."""
        start = os.getcwd()
        with tempfile.TemporaryDirectory(prefix="pyshell test ") as tmpdir:
            try:
                os.chdir(tmpdir)
                ex = Executor()
                p = ex.get_prompt()
                # Base name is like "pyshell test abc123"
                base = os.path.basename(tmpdir)
                self.assertIn(base, p)
            finally:
                os.chdir(start)

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

    def test_get_jobs_returns_snapshot(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        self.assertEqual(ex.get_jobs(), [])
        ex.run_command([sys.executable, "-c", "import time; time.sleep(0.1)"], background=True)
        jobs = ex.get_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertIn("id", jobs[0])
        self.assertIn("cmd", jobs[0])
        self.assertIn("status", jobs[0])
        self.assertIn("pid", jobs[0])
        self.assertIn("running", jobs[0]["status"])
        ex._jobs[0]["procs"][0].wait()
        ex._jobs.clear()

    def test_kill_builtin_accepts_job_spec(self):
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_command([sys.executable, "-c", "import time; time.sleep(10)"], background=True)
        self.assertEqual(len(ex._jobs), 1)
        job_id = ex._jobs[0]["id"]
        ex.run_command(["kill", "%" + str(job_id)])
        # Process should be gone (or exit code 1 if already reaped)
        ex._jobs[0]["procs"][0].wait(timeout=2)
        self.assertIn(ex._last_exit_code, (0, 1))
        ex._jobs.clear()


class TestJobControlSuspend(unittest.TestCase):
    """Suspend (Ctrl+Z) and job control: available on Unix with TTY, not on Windows."""

    def test_job_control_available_false_on_windows(self):
        """On Windows, job control (suspend) is not available."""
        if os.name != "nt":
            self.skipTest("Windows only")
        self.assertFalse(_job_control_available())

    def test_job_control_available_false_without_tty(self):
        """When stdin is not a TTY (e.g. pytest), job control is not used."""
        # In pytest stdin is typically not a TTY; so we expect False on both platforms
        if sys.stdin.isatty():
            self.skipTest("Requires non-TTY stdin (e.g. pytest)")
        self.assertFalse(_job_control_available())

    def test_background_then_fg_completes_on_windows(self):
        """On Windows, background job + fg still completes and sets exit code."""
        if os.name != "nt":
            self.skipTest("Windows only")
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        ex.run_command(
            [sys.executable, "-c", "import sys; sys.exit(42)"],
            background=True,
        )
        self.assertEqual(len(ex._jobs), 1)
        out = io.StringIO()
        with redirect_stdout(out):
            ex.run_command(["fg"])
        self.assertEqual(ex._last_exit_code, 42)
        self.assertEqual(len(ex._jobs), 0)

    @unittest.skipIf(os.name == "nt", "Unix job control: suspend/fg with stopped jobs")
    def test_jobs_shows_stopped_on_unix(self):
        """On Unix, a stopped process in the job list is shown as 'stopped' by jobs."""
        if not hasattr(os, "WIFSTOPPED"):
            self.skipTest("No WIFSTOPPED (Unix job control)")
        ex = Executor()
        ex.set_exit_callback(lambda code: None)
        # Start a process that we can stop with SIGTSTP
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(999)"],
            start_new_session=True,
        )
        try:
            os.kill(proc.pid, signal.SIGTSTP)
            time.sleep(0.2)
            _, st = os.waitpid(proc.pid, os.WNOHANG | os.WUNTRACED)
            if not os.WIFSTOPPED(st):
                self.skipTest("Process did not stop (no TTY?)")
            ex._jobs.append({
                "id": 1,
                "procs": [proc],
                "cmd": "sleep 999",
                "pgid": proc.pid,
            })
            out = io.StringIO()
            with redirect_stdout(out):
                ex.run_command(["jobs"])
            self.assertIn("stopped", out.getvalue().lower())
        finally:
            try:
                os.kill(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                proc.wait()
            except Exception:
                pass


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
