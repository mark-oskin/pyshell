"""Main REPL and shell orchestration.

Entry point: main(). Shell runs the read-eval loop, line reading (readline or
Windows fallback), history load/save, and .pyshellrc. It uses the parser to
classify lines and the executor to run Python or commands/pipelines.
"""

import os
import subprocess
import sys
from pyshell.parser import (
    parse_line,
    parse_redirects,
    has_unquoted_redirect_or_background,
    has_conditional,
    split_conditional,
)
from pyshell.executor import Executor

try:
    import readline  # noqa: F401 - enables history when available
except ImportError:
    readline = None  # type: ignore

if os.name == "nt":
    try:
        import msvcrt  # noqa: F401
    except ImportError:
        msvcrt = None  # type: ignore
else:
    msvcrt = None  # type: ignore


def main() -> int:
    """CLI entry: run REPL, script, or -c command.

    Parses argv for -h, -v, --no-rc, -c CMD, and optional SCRIPT path.
    Returns exit code (0 on success).
    """
    from pyshell import __version__
    argv = sys.argv[1:]
    no_rc = False
    cmd_c = None
    script_path = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--help", "-h"):
            _print_usage()
            return 0
        if a in ("--version", "-v"):
            print(__version__)
            return 0
        if a == "--no-rc":
            no_rc = True
            i += 1
            continue
        if a == "-c":
            if i + 1 >= len(argv):
                print("pyshell: -c requires an argument", file=sys.stderr)
                return 1
            cmd_c = argv[i + 1]
            i += 2
            continue
        if a.startswith("-"):
            print(f"pyshell: unknown option: {a}", file=sys.stderr)
            return 1
        script_path = a
        i += 1
        break
    if cmd_c:
        shell = Shell()
        shell.executor.set_exit_callback(shell.request_exit)
        shell.executor.set_history_callback(shell.get_history)
        shell.executor.set_shell_helper(ShellHelper(shell))
        try:
            result = shell._eval(cmd_c)
            if result is not None and result != "":
                print(result)
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        return shell.executor._last_exit_code
    if script_path:
        return run_script(script_path)
    shell = Shell()
    return shell.run(run_rc=not no_rc)


class ShellHelper:
    """Helper exposed as `shell` in the Python namespace.

    Provides run(cmd), capture(cmd), cd, pwd, pushd, popd, dirs, jobs, fg, bg, kill,
    exit_code, and prompt for use from Python code or scripts.
    """

    def __init__(self, shell: "Shell") -> None:
        """Store reference to the Shell instance."""
        self._shell = shell

    def run(self, cmd: str, background: bool = False) -> int:
        """Run one shell command line. Returns exit code.

        If background is True, runs the command in the background (adds to job list).
        """
        line = cmd.strip()
        if background and line and not line.endswith("&"):
            line = line + " &"
        self._shell._eval(line)
        return self._shell.executor._last_exit_code

    def capture(self, cmd: str) -> tuple[str, int]:
        """Run command and capture stdout. Returns (output_string, exit_code)."""
        return self._shell._run_and_capture(cmd)

    def cd(self, path: str = "") -> None:
        """Change current directory; no args = home (~)."""
        self._shell.executor.run_command(["cd", path] if path else ["cd"])

    def pwd(self) -> str:
        """Return current working directory."""
        return os.getcwd()

    def pushd(self, path: str = "") -> None:
        """Push cwd onto stack and cd to path; no path = swap cwd with top of stack."""
        argv = ["pushd", path] if path else ["pushd"]
        self._shell.executor.run_command(argv)

    def popd(self) -> None:
        """Pop directory from stack and cd to it."""
        self._shell.executor.run_command(["popd"])

    def dirs(self) -> str:
        """Return directory stack (cwd and pushd stack) as a string."""
        result = self._shell.executor.run_command(["dirs"])
        return result if isinstance(result, str) else ""

    def jobs(self) -> list[dict]:
        """Return list of jobs. Each dict has id, cmd, status ('running'|'stopped'|'done'), pid."""
        return self._shell.executor.get_jobs()

    def fg(self, spec: str | None = None) -> int:
        """Bring a job to the foreground; wait for it. spec: None or '%n' (e.g. '%1'). Returns exit code."""
        argv = ["fg", spec] if spec else ["fg"]
        self._shell.executor.run_command(argv)
        return self._shell.executor._last_exit_code

    def bg(self, spec: str | None = None) -> int:
        """Resume a stopped job in the background. spec: None or '%n'. Returns exit code (0 on success)."""
        argv = ["bg", spec] if spec else ["bg"]
        self._shell.executor.run_command(argv)
        return self._shell.executor._last_exit_code

    def kill(self, *args: str) -> int:
        """Send signal to process or job. E.g. kill('%1'), kill('-9', '%1'), kill('12345'). Returns exit code."""
        self._shell.executor.run_command(["kill"] + list(args))
        return self._shell.executor._last_exit_code

    def exit_code(self) -> int:
        """Return the exit code of the last run command or pipeline."""
        return self._shell.executor._last_exit_code

    def prompt(self, template: str | None = None) -> str:
        """Get or set the REPL prompt. prompt() returns current prompt; prompt(template) sets it and returns ''."""
        if template is not None:
            self._shell.executor.set_prompt(template)
            return ""
        return self._shell.executor.get_prompt()


def _print_usage() -> None:
    """Print pyshell usage to stdout."""
    print("Usage: pyshell [OPTIONS] [SCRIPT]")
    print()
    print("  Start an interactive shell, or run a script if SCRIPT is given.")
    print()
    print("Options:")
    print("  -c CMD         Run CMD and exit (single command)")
    print("  -h, --help     Show this message and exit")
    print("  --no-rc        Do not load .pyshellrc on startup")
    print("  -v, --version  Print version and exit")
    print()
    print("  In the shell: help for builtins; help prompt, help quoting, help windows for docs.")


def run_script(path: str) -> int:
    """Execute a pyshell script file in a new Shell.

    Args:
        path: Path to script file.

    Returns:
        Exit code (0 on success; 127 on read error).
    """
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read()
    except OSError as e:
        print(f"pyshell: {e}", file=sys.stderr)
        return 127
    shell = Shell()
    shell.executor.set_exit_callback(shell.request_exit)
    exit_code = 0
    buffer: list[str] = []
    for raw in lines.split("\n"):
        if buffer and raw.strip().endswith("\\"):
            buffer.append(raw.strip()[:-1])
            continue
        if buffer:
            line = "\n".join(buffer) + "\n" + raw
            buffer = []
        else:
            line = raw
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            result = shell._eval(line)
            if result is not None and result != "":
                print(result)
        except SystemExit as e:
            exit_code = e.code if isinstance(e.code, int) else 0
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            exit_code = 1
    if buffer:
        line = "\n".join(buffer).strip()
        if line:
            try:
                shell._eval(line)
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                exit_code = 1
    return exit_code or shell.executor._last_exit_code


class Shell:
    """Interactive shell: REPL loop, line reading, history, and eval dispatch.

    Uses parser for classification and executor for Python/command/pipeline
    execution. Handles readline vs Windows fallback and persistent history.
    """

    def __init__(self) -> None:
        self.executor = Executor()
        self._running = True
        self._history: list[str] = []
        self._completion_matches: list[str] = []

    def run(self, run_rc: bool = True) -> int:
        """Run the read-eval-print loop. Returns exit code. run_rc=False skips .pyshellrc."""
        self.executor.set_exit_callback(self.request_exit)
        self.executor.set_history_callback(self.get_history)
        self.executor.set_source_callback(self._run_file_in_current_shell)
        self.executor.set_shell_helper(ShellHelper(self))
        if readline is not None:
            self._setup_completion()
        if run_rc:
            self._run_startup_config()
        self._print_banner()
        self._load_history()
        exit_code = 0
        try:
            while self._running:
                try:
                    line = self._read_line()
                    if line is None:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    self._add_history(line)
                    result = self._eval(line)
                    if result is not None and result != "":
                        print(result)
                except EOFError:
                    break
                except KeyboardInterrupt:
                    print()
                    continue
                except SystemExit as e:
                    exit_code = e.code if isinstance(e.code, int) else 0
                    break
                except Exception as e:
                    print(f"Error: {e}", file=sys.stderr)
        finally:
            self._save_history()
        return exit_code

    def _run_file_in_current_shell(self, path: str) -> None:
        """Run a script file in the current shell (same namespace). Used by source / ."""
        path = os.path.expanduser(path)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            raise OSError(f"cannot read {path}: {e}") from e
        buffer: list[str] = []
        for raw in content.split("\n"):
            if buffer and raw.strip().endswith("\\"):
                buffer.append(raw.strip()[:-1])
                continue
            if buffer:
                line = "\n".join(buffer) + "\n" + raw
                buffer = []
            else:
                line = raw
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                result = self._eval(line)
                if result is not None and result != "":
                    print(result)
            except SystemExit:
                raise
            except Exception as e:
                print(f"Error: {e}", file=sys.stderr)
                raise
        if buffer:
            line = "\n".join(buffer).strip()
            if line:
                try:
                    self._eval(line)
                except SystemExit:
                    raise
                except Exception as e:
                    print(f"Error: {e}", file=sys.stderr)
                    raise

    def _run_startup_config(self) -> None:
        """Run .pyshellrc from cwd or home if present."""
        for base in [os.getcwd(), os.path.expanduser("~")]:
            path = os.path.join(base, ".pyshellrc")
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        content = f.read()
                except OSError:
                    continue
                buffer: list[str] = []
                for raw in content.split("\n"):
                    if buffer and raw.strip().endswith("\\"):
                        buffer.append(raw.strip()[:-1])
                        continue
                    if buffer:
                        line = "\n".join(buffer) + "\n" + raw
                        buffer = []
                    else:
                        line = raw
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        result = self._eval(line)
                        if result is not None and result != "":
                            print(result)
                    except SystemExit:
                        raise
                    except Exception:
                        pass
                if buffer:
                    line = "\n".join(buffer).strip()
                    if line:
                        try:
                            self._eval(line)
                        except Exception:
                            pass
                break

    def _print_banner(self) -> None:
        print("pyshell -- Python-like shell. Type exit() or Ctrl+D to quit.")
        print()

    def _add_history(self, line: str) -> None:
        """Append line to history and readline (if available)."""
        if not line:
            return
        self._history.append(line)
        if readline is not None:
            try:
                readline.add_history(line)
            except Exception:
                pass

    _HISTORY_FILENAME = ".pyshell_history"
    _HISTORY_MAX_ENTRIES = 2000

    def _history_file_path(self) -> str:
        """Path to the persistent history file (e.g. ~/.pyshell_history)."""
        return os.path.join(os.path.expanduser("~"), self._HISTORY_FILENAME)

    def _load_history(self) -> None:
        """Load history from file into _history and readline (if available)."""
        path = self._history_file_path()
        try:
            with open(path, encoding="utf-8") as f:
                raw_lines = f.readlines()
        except OSError:
            return
        for raw in raw_lines:
            line = raw.rstrip("\n")
            # Unescape: \\ -> \, \\n -> newline, \\r -> carriage return
            line = line.replace("\\\\", "\x00").replace("\\n", "\n").replace("\\r", "\r").replace("\x00", "\\")
            if not line:
                continue
            self._history.append(line)
            if readline is not None:
                try:
                    readline.add_history(line)
                except Exception:
                    pass
        if len(self._history) > self._HISTORY_MAX_ENTRIES:
            self._history = self._history[-self._HISTORY_MAX_ENTRIES :]
            if readline is not None:
                try:
                    readline.clear_history()
                    for h in self._history:
                        readline.add_history(h)
                except Exception:
                    pass

    def _save_history(self) -> None:
        """Write _history to file (last _HISTORY_MAX_ENTRIES), for persistence."""
        path = self._history_file_path()
        entries = self._history[-self._HISTORY_MAX_ENTRIES :]
        try:
            with open(path, "w", encoding="utf-8") as f:
                for line in entries:
                    escaped = line.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
                    f.write(escaped + "\n")
        except OSError:
            pass

    def _setup_completion(self) -> None:
        """Register tab completer and fix backspace binding for readline."""
        if readline is None:
            return
        readline.set_completer(self._completer)
        readline.parse_and_bind("tab: complete")
        # WSL2/Linux: ensure Backspace and DEL both delete backward (avoid \r / prompt wipe).
        try:
            readline.parse_and_bind(r'"\C-h": backward-delete-char')   # Ctrl+H (Backspace on some terms)
            readline.parse_and_bind(r'"\C-?": backward-delete-char')   # DEL (Backspace on many terms)
        except (TypeError, ValueError):
            pass

    def _completer(self, text: str, state: int):
        """Readline completer: (text, state) -> next completion or None."""
        if state == 0:
            self._completion_matches = self._get_completions(text)
        if state < len(self._completion_matches):
            return self._completion_matches[state]
        return None

    def _get_completions(self, text: str) -> list[str]:
        """Return list of completions for the given word."""
        try:
            line = readline.get_line_buffer() if readline else ""
            beg = readline.get_begidx() if readline else 0
            end = readline.get_endidx() if readline else len(text or "")
        except Exception:
            line = ""
            beg = 0
            end = len(text or "")
        raw_word = text if text is not None else (line[beg:end] if beg < len(line) else "")
        prefix_lower = raw_word.lower() if raw_word else ""
        completions: list[str] = []
        before_cursor = line[:beg]
        # On Windows (and when readline is a stub), get_line_buffer() often returns "";
        # then we cannot tell first vs later token, so we merge command + path completions.
        no_line_context = not line.strip() and bool(raw_word)
        tokens_before = before_cursor.strip().split()
        is_first_token = len(tokens_before) == 0
        do_command = is_first_token or (raw_word and raw_word.startswith("$")) or no_line_context
        do_path = not is_first_token or no_line_context

        if do_command:
            if raw_word and raw_word.startswith("$"):
                var_prefix = (raw_word[1:] or "").lower()
                for k in os.environ:
                    if k.startswith(var_prefix.upper()) or k.upper().startswith(var_prefix.upper()):
                        completions.append("$" + k)
                ns = self.executor._get_namespace()
                for k in ns:
                    if isinstance(k, str) and (k.startswith(var_prefix) or k.upper().startswith(var_prefix.upper())):
                        if k not in ("PATH",) or var_prefix:
                            completions.append("$" + k)
            elif not (raw_word and raw_word.startswith("$")):
                builtins = ["cd", "pwd", "exit", "env", "run", "run_capture", "history", "alias", "unalias", "prompt", "help", "jobs", "fg", "bg", "kill", "pushd", "popd", "dirs", "type", "which", "source"]
                if os.name == "nt":
                    builtins = builtins + ["ls", "dir", "cat", "echo"]
                for b in builtins:
                    if b.lower().startswith(prefix_lower):
                        completions.append(b)
                path_env = os.environ.get("PATH", "")
                for d in path_env.split(os.pathsep):
                    if not d:
                        continue
                    try:
                        for name in os.listdir(d):
                            if name.lower().startswith(prefix_lower) and os.access(os.path.join(d, name), os.X_OK):
                                if name not in completions:
                                    completions.append(name)
                    except OSError:
                        pass
        if do_path:
            # Path completion: preserve case of prefix for path parsing, match case-insensitively
            dir_part = os.path.dirname(raw_word)
            file_part = os.path.basename(raw_word)
            try:
                search_dir = os.path.normpath(os.path.join(os.getcwd(), dir_part)) if dir_part else os.getcwd()
                for name in os.listdir(search_dir):
                    if not name.lower().startswith((file_part or prefix_lower).lower()):
                        continue
                    p = os.path.join(search_dir, name)
                    if os.path.isdir(p):
                        completions.append(os.path.join(dir_part, name) + os.sep if dir_part else name + os.sep)
                    else:
                        completions.append(os.path.join(dir_part, name) if dir_part else name)
            except OSError:
                pass
        return sorted(set(completions))

    def _has_unclosed_delimiters(self, text: str) -> bool:
        """True if text has unclosed brackets or quotes (so we need more input)."""
        i = 0
        n = len(text)
        stack: list[str] = []  # expected close chars
        in_triple_dq = False
        in_triple_sq = False
        while i < n:
            if in_triple_dq:
                if text[i : i + 3] == '"""':
                    i += 3
                    in_triple_dq = False
                    continue
                i += 1
                continue
            if in_triple_sq:
                if text[i : i + 3] == "'''":
                    i += 3
                    in_triple_sq = False
                    continue
                i += 1
                continue
            if text[i : i + 3] == '"""':
                in_triple_dq = True
                i += 3
                continue
            if text[i : i + 3] == "'''":
                in_triple_sq = True
                i += 3
                continue
            c = text[i]
            if c == "\\" and i + 1 < n and text[i + 1] in '"\'\\':
                i += 2
                continue
            if stack and stack[-1] in ("'", '"'):
                if c == stack[-1]:
                    stack.pop()
                i += 1
                continue
            if c == "(":
                stack.append(")")
                i += 1
                continue
            if c == "[":
                stack.append("]")
                i += 1
                continue
            if c == "{":
                stack.append("}")
                i += 1
                continue
            if c in ")]}":
                if stack and stack[-1] == c:
                    stack.pop()
                i += 1
                continue
            if c == '"':
                stack.append('"')
                i += 1
                continue
            if c == "'":
                stack.append("'")
                i += 1
                continue
            i += 1
        return bool(stack) or in_triple_dq or in_triple_sq

    def _find_matching_paren(self, s: str, open_idx: int) -> int:
        """Return index of the ')' that matches s[open_idx] == '(', respecting quotes. -1 if not found."""
        n = len(s)
        if open_idx >= n or s[open_idx] != "(":
            return -1
        depth = 1
        i = open_idx + 1
        in_triple_dq = False
        in_triple_sq = False
        quote = None
        while i < n:
            if in_triple_dq:
                if s[i : i + 3] == '"""':
                    i += 3
                    in_triple_dq = False
                    continue
                i += 1
                continue
            if in_triple_sq:
                if s[i : i + 3] == "'''":
                    i += 3
                    in_triple_sq = False
                    continue
                i += 1
                continue
            if quote is not None:
                if s[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if s[i] == quote:
                    quote = None
                i += 1
                continue
            if s[i : i + 3] == '"""':
                in_triple_dq = True
                i += 3
                continue
            if s[i : i + 3] == "'''":
                in_triple_sq = True
                i += 3
                continue
            if s[i] in "'\"":
                quote = s[i]
                i += 1
                continue
            if s[i] == "(":
                depth += 1
                i += 1
                continue
            if s[i] == ")":
                depth -= 1
                if depth == 0:
                    return i
                i += 1
                continue
            i += 1
        return -1

    def _is_subshell(self, line: str) -> bool:
        """True if line is ( ... ) subshell form: leading '(' and matching ')' at end (not $(...))."""
        stripped = line.strip()
        if not stripped.startswith("(") or stripped.startswith("$("):
            return False
        close = self._find_matching_paren(stripped, 0)
        if close == -1:
            return False
        if stripped[close + 1 :].strip():
            return False
        return True

    def _extract_subshell_content(self, line: str) -> str:
        """Return the inner content of ( ... ) for subshell execution."""
        stripped = line.strip()
        close = self._find_matching_paren(stripped, 0)
        if close == -1:
            return stripped
        return stripped[1:close].strip()

    def _run_subshell(self, inner: str) -> None:
        """Run inner command line in a new pyshell process; print output and set last exit code."""
        proc = subprocess.run(
            [sys.executable, "-m", "pyshell", "-c", inner],
            capture_output=True,
            text=True,
        )
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        self.executor._set_exit_code(proc.returncode if proc.returncode is not None else 0)

    def _read_line_fallback(self, prompt: str) -> str | None:
        """Read one line key-by-key (Windows fallback when readline unavailable).

        Handles history (Up/Down), cursor (Left/Right, Home/End, Ctrl+A/E),
        backspace, tab completion, and Ctrl+C/Ctrl+Z.

        Args:
            prompt: Prompt string already printed by caller.

        Returns:
            Entered line or None on EOF (Ctrl+Z or Ctrl+D).
        """
        if msvcrt is None:
            # Unix/WSL: pass prompt to input() so readline knows prompt length; backspace then
            # deletes only within the line instead of moving to BOL and wiping the prompt.
            # (Backspace binding is set in _setup_completion.)
            try:
                return input(prompt)
            except EOFError:
                return None
        # Windows: key-by-key with msvcrt, our own completion and history (Up/Down)
        sys.stdout.write(prompt)
        sys.stdout.flush()
        line = ""
        pos = 0  # cursor index in line (0..len(line))
        history = self._history
        history_index = len(history)  # beyond last = "current line" being edited
        current_edit = ""  # line being typed before we started navigating history
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return line
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if ch == "\x1a":  # Ctrl+Z (traditional Windows EOF)
                raise EOFError
            if ch == "\x04":  # Ctrl+D (Linux-style EOF; also work on Windows)
                raise EOFError
            if ch == "\x01":  # Ctrl+A: beginning of line
                if pos > 0:
                    sys.stdout.write("\b" * pos)
                    sys.stdout.flush()
                    pos = 0
                continue
            if ch == "\x05":  # Ctrl+E: end of line
                if pos < len(line):
                    sys.stdout.write(line[pos:])
                    sys.stdout.flush()
                    pos = len(line)
                continue
            if ch in ("\x00", "\xe0"):  # special key prefix, then scan code
                scan = msvcrt.getwch()
                if ch == "\xe0" and scan in ("H", "P"):  # Up=72, Down=80
                    if scan == "H":  # Up: previous history
                        if history:
                            if history_index >= len(history):
                                current_edit = line
                            history_index = max(0, history_index - 1)
                            line = history[history_index]
                            pos = len(line)
                            n = len(prompt) + max(len(line), 80)
                            sys.stdout.write("\r" + " " * n + "\r" + prompt + line)
                            sys.stdout.flush()
                    else:  # Down: next history
                        if history:
                            history_index = min(len(history), history_index + 1)
                            if history_index >= len(history):
                                line = current_edit
                            else:
                                line = history[history_index]
                            pos = len(line)
                            n = len(prompt) + max(len(line), 80)
                            sys.stdout.write("\r" + " " * n + "\r" + prompt + line)
                            sys.stdout.flush()
                elif ch == "\xe0" and scan == "K":  # Left
                    if pos > 0:
                        pos -= 1
                        sys.stdout.write("\b")
                        sys.stdout.flush()
                elif ch == "\xe0" and scan == "M":  # Right
                    if pos < len(line):
                        sys.stdout.write(line[pos])
                        pos += 1
                        sys.stdout.flush()
                elif ch == "\xe0" and scan == "G":  # Home
                    if pos > 0:
                        sys.stdout.write("\b" * pos)
                        sys.stdout.flush()
                        pos = 0
                elif ch == "\xe0" and scan == "O":  # End
                    if pos < len(line):
                        sys.stdout.write(line[pos:])
                        sys.stdout.flush()
                        pos = len(line)
                continue
            if ch == "\b" or ch == "\x7f":  # backspace
                if pos > 0:
                    line = line[: pos - 1] + line[pos:]
                    pos -= 1
                    sys.stdout.write("\b")
                    sys.stdout.write(line[pos:] + " ")
                    sys.stdout.write("\b" * (len(line) - pos + 1))
                    sys.stdout.flush()
                continue
            if ch == "\t":  # Tab: complete
                tokens = line.split()
                word = tokens[-1] if tokens else ""
                completions = self._get_completions(word)
                if not completions:
                    continue
                if len(completions) == 1:
                    replacement = completions[0]
                    if not replacement.endswith(os.sep):
                        replacement += " "
                    line = line[: -len(word)] + replacement if word else line + replacement
                else:
                    # common prefix
                    prefix = os.path.commonprefix(completions)
                    if prefix and prefix != word:
                        line = line[: -len(word)] + prefix if word else line + prefix
                    else:
                        # show list and redraw
                        sys.stdout.write("\n")
                        for c in sorted(completions)[:20]:
                            sys.stdout.write(c + "  ")
                        sys.stdout.write("\n")
                        sys.stdout.write(prompt + line)
                        sys.stdout.flush()
                        pos = len(line)
                        continue
                pos = len(line)
                n = len(prompt) + len(line)
                sys.stdout.write("\r" + " " * n + "\r" + prompt + line)
                sys.stdout.flush()
                continue
            # Typing: insert at cursor
            history_index = len(history)
            if pos < len(line):
                line = line[:pos] + ch + line[pos:]
                pos += 1
                sys.stdout.write(ch)
                sys.stdout.write(line[pos:])
                sys.stdout.write("\b" * (len(line) - pos))
            else:
                line += ch
                pos += 1
                sys.stdout.write(ch)
            sys.stdout.flush()

    def _read_line(self) -> str | None:
        r"""Read a line with optional continuation (trailing \ and unclosed delimiters)."""
        try:
            prompt = self.executor.get_prompt()
            # Never pass prompt to input(): readline truncates at first space (and at U+00A0).
            # Always use fallback so we write the full prompt then input(); works on Windows and Linux/WSL.
            line = self._read_line_fallback(prompt)
            if line is None:
                return None
        except EOFError:
            return None
        while line.endswith("\\"):
            line = line[:-1]
            try:
                cont = input("... ") if readline is not None else self._read_line_fallback("... ")
                if cont is None:
                    return line.strip() or None
                line += "\n" + cont
            except EOFError:
                return line.strip() or None
        while self._has_unclosed_delimiters(line):
            try:
                cont = input("... ") if readline is not None else self._read_line_fallback("... ")
                if cont is None:
                    return line.strip() or None
                line += "\n" + cont
            except EOFError:
                return line.strip() or None
        return line

    def _run_and_capture(self, line: str) -> tuple[str, int]:
        """Run one line through _eval, capture stdout, return (output, exit_code).
        Use a real pipe (not StringIO) so pipelines get a real fd and produce output on all platforms.
        """
        old_stdout = sys.stdout
        rfd, wfd = os.pipe()
        enc = getattr(old_stdout, "encoding", None) or "utf-8"
        write_pipe = open(wfd, "w", encoding=enc)  # noqa: SIM115
        sys.stdout = write_pipe
        try:
            self._eval(line.strip())
        finally:
            write_pipe.close()
            sys.stdout = old_stdout
        with open(rfd, "r", encoding=enc) as read_pipe:
            output = read_pipe.read()
        return (output, self.executor._last_exit_code)

    def _expand_command_substitution(self, line: str, depth: int = 0) -> str:
        """Replace $(...) and `...` with command output. Max depth 5 to avoid infinite recursion."""
        if depth > 5:
            return line
        result = line
        # Backticks: `cmd` -> same as $(cmd)
        i = 0
        while i < len(result):
            if result[i] == "`":
                j = result.find("`", i + 1)
                if j == -1:
                    break
                sub = result[i + 1 : j].strip()
                out, _ = self._run_and_capture(sub)
                result = result[:i] + out.rstrip("\n") + result[j + 1 :]
                i = 0
                continue
            if result[i] == "$" and i + 1 < len(result) and result[i + 1] == "(":
                depth_paren = 1
                j = i + 2
                while j < len(result) and depth_paren > 0:
                    if result[j] == "(":
                        depth_paren += 1
                    elif result[j] == ")":
                        depth_paren -= 1
                    j += 1
                if depth_paren == 0:
                    sub = result[i + 2 : j - 1].strip()
                    out, _ = self._run_and_capture(sub)
                    result = result[:i] + out.rstrip("\n") + result[j:]
                    i = 0
                    continue
            i += 1
        return result

    def _expand_aliases(self, line: str, depth: int = 0) -> str:
        """Expand first word if it is an alias. Max depth 10 to avoid infinite loops."""
        if depth > 10:
            return line
        s = line.strip()
        if not s:
            return line
        parts = s.split(None, 1)
        first = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if first in self.executor._aliases:
            expanded = self.executor._aliases[first] + (" " + rest if rest else "")
            return self._expand_aliases(expanded, depth + 1)
        return line

    def _eval(self, line: str):
        """Parse and execute one line; return result for printing or None."""
        line = self._expand_aliases(line)
        if self._is_subshell(line):
            inner = self._extract_subshell_content(line)
            if inner:
                self._run_subshell(inner)
            return None
        # If line is valid Python and has no redirect/background, run as Python directly
        # so quoted strings (e.g. print("hello")) are not mangled by parse_redirects.
        if not has_unquoted_redirect_or_background(line):
            try:
                kind, payload = parse_line(line)
                if kind == "python" and payload:
                    return self.executor.run_python(payload, line)
            except Exception:
                pass
        line = self._expand_command_substitution(line)
        argv, redirects, background = parse_redirects(line)
        cmd_line = " ".join(argv)
        if not cmd_line.strip():
            return None
        if has_conditional(cmd_line):
            return self._eval_conditional(split_conditional(cmd_line), redirects, background)
        kind, payload = parse_line(cmd_line)
        if kind == "python":
            return self.executor.run_python(payload, cmd_line)
        if kind == "command":
            return self.executor.run_command(payload, redirects=redirects, background=background)
        if kind == "pipeline":
            return self.executor.run_pipeline(payload, redirects=redirects, background=background)
        return None

    def _eval_conditional(
        self,
        chain: list[tuple[str, str | None]],
        redirects: list,
        background: bool,
    ):
        """Run a chain of segments connected by && and ||. Only last segment gets redirects/background."""
        result = None
        for i, (seg, connector) in enumerate(chain):
            if not seg.strip():
                continue
            seg = self._expand_aliases(seg)
            if not seg.strip():
                continue
            is_last = i == len(chain) - 1
            redir = redirects if is_last else []
            bg = background if is_last else False
            result = self._eval_one(seg, redirects=redir, background=bg)
            code = self.executor._last_exit_code
            if connector == "&&" and code != 0:
                break
            if connector == "||" and code == 0:
                break
        return result

    def _eval_one(self, cmd_line: str, redirects: list, background: bool):
        """Parse and run one command or pipeline (no conditional splitting)."""
        kind, payload = parse_line(cmd_line)
        if kind == "python":
            return self.executor.run_python(payload, cmd_line)
        if kind == "command":
            return self.executor.run_command(payload, redirects=redirects, background=background)
        if kind == "pipeline":
            return self.executor.run_pipeline(payload, redirects=redirects, background=background)
        return None

    def get_history(self) -> list[str]:
        """Return a copy of the current history list (for history builtin)."""
        return list(self._history)

    def request_exit(self, code: int = 0) -> None:
        """Stop the REPL and raise SystemExit(code)."""
        self._running = False
        raise SystemExit(code)
