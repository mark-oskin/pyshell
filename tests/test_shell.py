"""Tests for shell: history and script execution."""

import os
import tempfile
import unittest
import unittest.mock

from pyshell.shell import Shell, run_script, main


class TestHistory(unittest.TestCase):
    """Command history is stored and available."""

    def test_history_starts_empty(self):
        shell = Shell()
        self.assertEqual(shell.get_history(), [])

    def test_add_history_append(self):
        shell = Shell()
        shell._add_history("ls")
        shell._add_history("pwd")
        self.assertEqual(shell.get_history(), ["ls", "pwd"])

    def test_history_after_eval(self):
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        shell.executor.set_history_callback(shell.get_history)
        shell._eval("2+3")
        shell._add_history("2+3")
        self.assertIn("2+3", shell.get_history())
        shell._eval("x = 1")
        shell._add_history("x = 1")
        self.assertEqual(len(shell.get_history()), 2)


class TestPythonQuotedString(unittest.TestCase):
    """Python lines with quoted strings must not be mangled by redirect parsing."""

    def test_print_hello_works(self):
        import io
        from contextlib import redirect_stdout
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        out = io.StringIO()
        with redirect_stdout(out):
            result = shell._eval('print("hello")')
        self.assertEqual(out.getvalue().strip(), "hello")
        self.assertIsNone(result)


class TestAliasExpansion(unittest.TestCase):
    def test_expand_alias(self):
        shell = Shell()
        shell.executor._aliases["ll"] = "ls -la"
        expanded = shell._expand_aliases("ll")
        self.assertEqual(expanded, "ls -la")

    def test_expand_alias_with_args(self):
        shell = Shell()
        shell.executor._aliases["ll"] = "ls -la"
        expanded = shell._expand_aliases("ll /tmp")
        self.assertEqual(expanded, "ls -la /tmp")

    def test_no_expand_unknown(self):
        shell = Shell()
        self.assertEqual(shell._expand_aliases("ls"), "ls")

    def test_alias_chain_depth_limited(self):
        shell = Shell()
        shell.executor._aliases["a"] = "b"
        shell.executor._aliases["b"] = "a"
        expanded = shell._expand_aliases("a")
        self.assertIn(expanded, ("a", "b"))


class TestStartupConfig(unittest.TestCase):
    """Startup config .pyshellrc is run at REPL start."""

    def test_pyshellrc_from_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            rc = os.path.join(d, ".pyshellrc")
            with open(rc, "w", encoding="utf-8") as f:
                f.write("alias ll=ls -la\n")
            start_cwd = os.getcwd()
            try:
                os.chdir(d)
                shell = Shell()
                shell.executor.set_exit_callback(lambda code: None)
                shell._run_startup_config()
                self.assertEqual(shell.executor._aliases.get("ll"), "ls -la")
            finally:
                os.chdir(start_cwd)

    def test_pyshellrc_skips_comments(self):
        with tempfile.TemporaryDirectory() as d:
            rc = os.path.join(d, ".pyshellrc")
            with open(rc, "w", encoding="utf-8") as f:
                f.write("# comment\nalias x=echo\n")
            start_cwd = os.getcwd()
            try:
                os.chdir(d)
                shell = Shell()
                shell.executor.set_exit_callback(lambda code: None)
                shell._run_startup_config()
                self.assertEqual(shell.executor._aliases.get("x"), "echo")
            finally:
                os.chdir(start_cwd)


class TestRunScript(unittest.TestCase):
    """Script execution runs a file of pyshell commands."""

    def test_run_script_simple(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".psh", delete=False) as f:
            f.write("2+3\n")
            path = f.name
        try:
            exit_code = run_script(path)
            self.assertEqual(exit_code, 0)
        finally:
            os.unlink(path)

    def test_run_script_prints_result(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".psh", delete=False) as f:
            f.write("2+3\n")
            path = f.name
        try:
            import io
            from contextlib import redirect_stdout
            out = io.StringIO()
            with redirect_stdout(out):
                # run_script prints result of last expression; we need to capture
                exit_code = run_script(path)
            self.assertEqual(out.getvalue().strip(), "5")
        finally:
            os.unlink(path)

    def test_run_script_sets_last_exit_code(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".psh", delete=False) as f:
            f.write("print(last_exit_code)\n")
            path = f.name
        try:
            import io
            from contextlib import redirect_stdout
            out = io.StringIO()
            with redirect_stdout(out):
                run_script(path)
            # last_exit_code should be 0 after print
            self.assertIn("0", out.getvalue())
        finally:
            os.unlink(path)

    def test_run_script_nonexistent_returns_127(self):
        exit_code = run_script("/nonexistent/path/script.psh")
        self.assertEqual(exit_code, 127)

    def test_run_script_skips_comments(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".psh", delete=False) as f:
            f.write("# comment\n1+1\n")
            path = f.name
        try:
            import io
            from contextlib import redirect_stdout
            out = io.StringIO()
            with redirect_stdout(out):
                run_script(path)
            self.assertEqual(out.getvalue().strip(), "2")
        finally:
            os.unlink(path)


class TestTabCompletion(unittest.TestCase):
    def test_get_completions_builtin_prefix(self):
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        # Force readline state so we're completing first token with prefix "pw"
        with unittest.mock.patch("pyshell.shell.readline") as m:
            m.get_line_buffer.return_value = "pw"
            m.get_begidx.return_value = 0
            m.get_endidx.return_value = 2
            completions = shell._get_completions("pw")
        self.assertIn("pwd", completions)

    def test_get_completions_empty_prefix(self):
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        with unittest.mock.patch("pyshell.shell.readline") as m:
            m.get_line_buffer.return_value = ""
            m.get_begidx.return_value = 0
            m.get_endidx.return_value = 0
            completions = shell._get_completions("")
        self.assertIn("pwd", completions)
        self.assertIn("exit", completions)

    def test_get_completions_second_word_is_path(self):
        """After 'cat RE', completions should be path names matching RE, not commands."""
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        with unittest.mock.patch("pyshell.shell.readline") as m:
            m.get_line_buffer.return_value = "cat RE"
            m.get_begidx.return_value = 4
            m.get_endidx.return_value = 6
            completions = shell._get_completions("RE")
        # Should not complete to commands (e.g. run, readline)
        self.assertNotIn("run", completions)
        # Should complete to paths in cwd matching RE (case-insensitive)
        self.assertIn("README.md", completions)

    def test_get_completions_no_line_buffer_includes_paths(self):
        """When line buffer is empty (e.g. Windows), completing 'RE' still offers path completions."""
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        with unittest.mock.patch("pyshell.shell.readline") as m:
            m.get_line_buffer.return_value = ""
            m.get_begidx.return_value = 0
            m.get_endidx.return_value = 2
            completions = shell._get_completions("RE")
        # Must include path completion (e.g. README.md) when buffer is unavailable
        self.assertIn("README.md", completions)


class TestConditionalExecution(unittest.TestCase):
    """&& and || short-circuit execution."""

    def test_and_stops_on_failure(self):
        import sys as _sys
        py = _sys.executable.replace("\\", "/")
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        out, code = shell._run_and_capture(f'{py} -c "print(1)" && {py} -c "print(2)"')
        self.assertEqual(code, 0)
        self.assertIn("1", out)
        self.assertIn("2", out)
        out2, code2 = shell._run_and_capture(
            f'{py} -c "print(1)" && {py} -c "import sys; sys.exit(1)" && {py} -c "print(2)"'
        )
        self.assertEqual(code2, 1)
        self.assertIn("1", out2)
        self.assertNotIn("2", out2)

    def test_or_stops_on_success(self):
        import sys as _sys
        py = _sys.executable.replace("\\", "/")
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        out, code = shell._run_and_capture(f'{py} -c "print(1)" || {py} -c "print(2)"')
        self.assertIn("1", out)
        self.assertNotIn("2", out)
        out2, code2 = shell._run_and_capture(
            f'{py} -c "import sys; sys.exit(1)" || {py} -c "print(3)"'
        )
        self.assertIn("3", out2)
        self.assertEqual(code2, 0)


class TestCommandSubstitution(unittest.TestCase):
    """$(...) and backticks expand to command output."""

    def test_dollar_paren_expands(self):
        import sys as _sys
        py = _sys.executable.replace("\\", "/")
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        # Use numeric output to avoid quote-stripping issues in subcommand
        expanded = shell._expand_command_substitution(f'prefix $({py} -c "print(42)") suffix')
        self.assertIn("42", expanded)
        self.assertIn("prefix", expanded)
        self.assertIn("suffix", expanded)

    def test_backtick_expands(self):
        import sys as _sys
        py = _sys.executable.replace("\\", "/")
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        expanded = shell._expand_command_substitution(f'x`{py} -c "print(99)"`y')
        self.assertIn("99", expanded)
        self.assertIn("x", expanded)
        self.assertIn("y", expanded)


class TestSource(unittest.TestCase):
    """source / . runs file in current shell."""

    def test_source_callback_called(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rc", delete=False) as f:
            f.write("x = 42\n")
            path = f.name
        try:
            shell = Shell()
            shell.executor.set_exit_callback(lambda code: None)
            shell.executor.set_source_callback(shell._run_file_in_current_shell)
            shell.executor.run_command(["source", path])
            ns = shell.executor._get_namespace()
            self.assertEqual(ns.get("x"), 42)
        finally:
            os.unlink(path)

    def test_dot_same_as_source(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".rc", delete=False) as f:
            f.write("y = 99\n")
            path = f.name
        try:
            shell = Shell()
            shell.executor.set_exit_callback(lambda code: None)
            shell.executor.set_source_callback(shell._run_file_in_current_shell)
            shell.executor.run_command([".", path])
            ns = shell.executor._get_namespace()
            self.assertEqual(ns.get("y"), 99)
        finally:
            os.unlink(path)

    def test_source_no_args_prints_error(self):
        import io
        from contextlib import redirect_stderr
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        shell.executor.set_source_callback(shell._run_file_in_current_shell)
        err = io.StringIO()
        with redirect_stderr(err):
            shell.executor.run_command(["source"])
        self.assertIn("missing file operand", err.getvalue())
        self.assertEqual(shell.executor._last_exit_code, 1)


class TestMultilineDelimiters(unittest.TestCase):
    """Unclosed brackets/quotes trigger continuation prompt."""

    def test_unclosed_paren(self):
        shell = Shell()
        self.assertTrue(shell._has_unclosed_delimiters("print("))

    def test_closed_paren(self):
        shell = Shell()
        self.assertFalse(shell._has_unclosed_delimiters("print(1)"))

    def test_unclosed_double_quote(self):
        shell = Shell()
        self.assertTrue(shell._has_unclosed_delimiters('echo "hello'))

    def test_triple_quote_unclosed(self):
        shell = Shell()
        self.assertTrue(shell._has_unclosed_delimiters('"""x'))


class TestHelpBuiltins(unittest.TestCase):
    """help lists all builtins with one-line descriptions."""

    def test_help_command_lists_all_builtins(self):
        import io
        from contextlib import redirect_stdout
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        out = io.StringIO()
        with redirect_stdout(out):
            shell.executor.run_command(["help"])
        text = out.getvalue()
        for name in ("source", "type", "which", "pushd", "popd", "dirs", "help"):
            self.assertIn(name, text, f"help output should mention {name}")

    def test_help_with_topic(self):
        import io
        from contextlib import redirect_stdout
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        out = io.StringIO()
        with redirect_stdout(out):
            shell.executor.run_command(["help", "source"])
        self.assertIn("source", out.getvalue())
        self.assertIn("script", out.getvalue().lower())


class TestSubshell(unittest.TestCase):
    """( ... ) runs commands in a subshell (new pyshell process)."""

    def test_subshell_runs_in_child(self):
        import io
        from contextlib import redirect_stdout
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        out = io.StringIO()
        with redirect_stdout(out):
            shell._eval("( pwd )")
        self.assertIn(os.getcwd(), out.getvalue() or "")

    def test_subshell_not_command_substitution(self):
        # ( echo x ) is subshell; $( echo x ) is command substitution
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        self.assertTrue(shell._is_subshell("( pwd )"))
        self.assertFalse(shell._is_subshell("$( pwd )"))

    def test_subshell_extract_content(self):
        shell = Shell()
        self.assertEqual(shell._extract_subshell_content("( cd /tmp && pwd )"), "cd /tmp && pwd")


class TestCLI(unittest.TestCase):
    """pyshell --help, --version, -c, --no-rc."""

    def test_help_flag(self):
        import io
        from contextlib import redirect_stdout
        with unittest.mock.patch("sys.argv", ["pyshell", "--help"]):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main()
        self.assertEqual(code, 0)
        self.assertIn("Usage:", out.getvalue())
        self.assertIn("-c", out.getvalue())
        self.assertIn("--no-rc", out.getvalue())

    def test_version_flag(self):
        import io
        from contextlib import redirect_stdout
        with unittest.mock.patch("sys.argv", ["pyshell", "--version"]):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main()
        self.assertEqual(code, 0)
        self.assertIn("0.1.0", out.getvalue())

    def test_c_flag_runs_command(self):
        import io
        from contextlib import redirect_stdout
        with unittest.mock.patch("sys.argv", ["pyshell", "-c", "print(42)"]):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main()
        self.assertEqual(code, 0)
        self.assertIn("42", out.getvalue())

    def test_no_rc_skips_startup(self):
        shell = Shell()
        shell.executor.set_exit_callback(lambda code: None)
        with unittest.mock.patch.object(shell, "_run_startup_config") as m_rc:
            with unittest.mock.patch.object(shell, "_read_line", return_value=None):
                code = shell.run(run_rc=False)
        m_rc.assert_not_called()
        self.assertEqual(code, 0)
