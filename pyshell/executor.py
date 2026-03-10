"""Execute Python code and shell commands."""

import ast
import os
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Any

try:
    import socket
except ImportError:
    socket = None  # type: ignore

from pyshell.builtins import (
    make_builtins,
    run_builtin_command,
    run_ls_dir,
    run_cat,
    run_echo,
    run_mkdir,
)
from pyshell.expansion import expand_command_argv, expand_redirect_path

# Type for redirect list: (op, path or None for 2>&1)
Redirects = list[tuple[str, str | None]]

BUILTIN_NAMES = frozenset({
    "cd", "pwd", "exit", "env", "run", "run_capture", "history", "alias", "unalias",
    "prompt", "help", "jobs", "fg", "bg", "pushd", "popd", "dirs", "source", "type", "which",
    "true", "false", "mkdir",
}) | (frozenset({"ls", "dir", "cat", "echo"}) if os.name == "nt" else frozenset())


class Executor:
    """Evaluates Python-like code and runs shell commands."""

    def __init__(self) -> None:
        self._namespace: dict[str, Any] = {}
        self._exit_callback: Any = None
        self._history_callback: Any = None
        self._last_exit_code: int = 0
        self._aliases: dict[str, str] = {}
        self._jobs: list[dict[str, Any]] = []
        self._next_job_id: int = 1
        self._prompt: str | None = None
        self._source_callback: Any = None
        self._dir_stack: list[str] = []
        self._shell_helper: Any = None

    def set_shell_helper(self, helper: Any) -> None:
        """Set the shell helper object (exposed as 'shell' in Python namespace)."""
        self._shell_helper = helper

    def set_exit_callback(self, callback: Any) -> None:
        self._exit_callback = callback

    def set_history_callback(self, callback: Any) -> None:
        self._history_callback = callback

    def set_prompt(self, s: str | None) -> None:
        """Set custom prompt string. Use {cwd} and {base} for current dir; None = default."""
        self._prompt = s

    def set_source_callback(self, callback: Any) -> None:
        """Set callback(path) to run a script in the current shell (source / .)."""
        self._source_callback = callback

    def get_aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def set_alias(self, name: str, value: str) -> None:
        self._aliases[name] = value

    def unalias(self, name: str) -> None:
        self._aliases.pop(name, None)

    def _get_namespace(self) -> dict[str, Any]:
        if self._exit_callback and "cd" not in self._namespace:
            self._namespace.update(
                make_builtins(
                    self._exit_callback,
                    self._history_callback,
                    self._aliases,
                    self.set_prompt,
                )
            )
        if "PATH" not in self._namespace:
            self._namespace.update(os.environ)
        # Expose last command exit code (updated after each command/pipeline)
        self._namespace["last_exit_code"] = self._last_exit_code
        if self._shell_helper is not None:
            self._namespace["shell"] = self._shell_helper
        return self._namespace

    def _set_exit_code(self, code: int) -> None:
        self._last_exit_code = code
        self._namespace["last_exit_code"] = code

    def get_prompt(self) -> str:
        """Return the REPL prompt (custom if set, else default with cwd)."""
        try:
            cwd = os.getcwd()
            base = os.path.basename(cwd)
            if base == os.path.sep or not base:
                base = cwd
        except OSError:
            cwd = ""
            base = ""
        user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        hostname = socket.gethostname() if socket else ""
        time_str = datetime.now().strftime("%H:%M:%S")
        exit_str = str(self._last_exit_code)
        jobs_str = str(len(self._jobs))
        if self._prompt is not None:
            s = self._prompt.replace("{cwd}", cwd).replace("{base}", base)
            s = s.replace("{user}", user).replace("{hostname}", hostname)
            s = s.replace("{time}", time_str).replace("{exit}", exit_str).replace("{jobs}", jobs_str)
            return s
        return f"[{base}] >>> "

    def run_python(self, source: str, original_line: str) -> Any:
        """
        Execute Python source. For expressions, return the value (for printing).
        For statements, return None (or last expression in interactive style).
        """
        ns = self._get_namespace()
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            raise SyntaxError(f"Invalid Python: {e}") from e

        if _is_expression_statement(tree):
            tree = ast.parse(original_line.strip(), mode="eval")
            value = eval(compile(tree, "<pyshell>", "eval"), ns)
            # Bare name that is callable → call it (e.g. pwd → pwd())
            if callable(value) and _is_bare_name(tree):
                value = value()
            return value
        # Statement(s)
        exec(compile(tree, "<pyshell>", "exec"), ns)
        return None

    def run_command(
        self,
        argv: list[str],
        redirects: Redirects | None = None,
        background: bool = False,
    ) -> Any:
        """Run a shell command (builtin or external). Returns output or None."""
        redirects = redirects or []
        if not argv:
            self._set_exit_code(0)
            return None
        env = self._get_namespace()
        argv = expand_command_argv(argv, env)
        redirects = [(op, expand_redirect_path(path, env)) for op, path in redirects]
        name, args = argv[0], argv[1:]
        if name == "type":
            if not args:
                print("type: missing argument", file=sys.stderr)
                self._set_exit_code(1)
                return None
            any_fail = False
            for n in args:
                if n in self._aliases:
                    print(f"{n} is aliased to `{self._aliases[n]}'")
                elif n in BUILTIN_NAMES or n == ".":
                    print(f"{n} is a shell builtin")
                else:
                    path = shutil.which(n)
                    if path:
                        print(f"{n} is {path}")
                    else:
                        print(f"type: {n}: not found", file=sys.stderr)
                        any_fail = True
            self._set_exit_code(1 if any_fail else 0)
            return None
        if name == "which":
            if not args:
                print("which: missing argument", file=sys.stderr)
                self._set_exit_code(1)
                return None
            any_fail = False
            for n in args:
                if n in self._aliases:
                    print(f"{n}: aliased to {self._aliases[n]}")
                elif n in BUILTIN_NAMES or n == ".":
                    # which typically doesn't print for builtins; we do for consistency
                    print(f"{n}: shell builtin")
                else:
                    path = shutil.which(n)
                    if path:
                        print(path)
                    else:
                        any_fail = True
            self._set_exit_code(1 if any_fail else 0)
            return None
        if name == "true":
            self._set_exit_code(0)
            return None
        if name == "false":
            self._set_exit_code(1)
            return None
        if name == "mkdir":
            ok = run_mkdir(argv)
            self._set_exit_code(0 if ok else 1)
            return None
        if name == "history" and self._history_callback is not None:
            for line in self._history_callback():
                print(line)
            self._set_exit_code(0)
            return None
        if name == "alias":
            if not args:
                for k, v in sorted(self._aliases.items()):
                    print(f"{k}={v}")
            else:
                rest = " ".join(args)
                if "=" in rest:
                    n, v = rest.split("=", 1)
                    self._aliases[n.strip()] = v.strip()
            self._set_exit_code(0)
            return None
        if name == "unalias":
            for a in args:
                self._aliases.pop(a, None)
            self._set_exit_code(0)
            return None
        if name == "jobs":
            _run_builtin_jobs(self._jobs)
            self._set_exit_code(0)
            return None
        if name == "fg":
            return _run_builtin_fg(self._jobs, self._set_exit_code)
        if name == "bg":
            _run_builtin_bg(self._jobs)
            self._set_exit_code(0)
            return None
        if name == "prompt":
            self.set_prompt(" ".join(args) if args else None)
            self._set_exit_code(0)
            return None
        if name == "pushd":
            cwd = os.getcwd()
            if args:
                path = expand_command_argv([args[0]], self._get_namespace())[0]
                path = os.path.expanduser(path)
                if not os.path.isdir(path):
                    print(f"pyshell: pushd: {path}: Not a directory", file=sys.stderr)
                    self._set_exit_code(1)
                    return None
                self._dir_stack.append(cwd)
                os.chdir(path)
            else:
                if not self._dir_stack:
                    print("pyshell: pushd: directory stack empty", file=sys.stderr)
                    self._set_exit_code(1)
                    return None
                target = self._dir_stack[-1]
                self._dir_stack[-1] = cwd
                os.chdir(target)
            self._set_exit_code(0)
            return None
        if name == "popd":
            if not self._dir_stack:
                print("pyshell: popd: directory stack empty", file=sys.stderr)
                self._set_exit_code(1)
                return None
            target = self._dir_stack.pop()
            os.chdir(target)
            self._set_exit_code(0)
            return None
        if name == "dirs":
            parts = [os.getcwd()] + list(reversed(self._dir_stack))
            self._set_exit_code(0)
            return " ".join(parts)
        if name in ("source", "."):
            if not args:
                print("pyshell: source: missing file operand", file=sys.stderr)
                self._set_exit_code(1)
                return None
            if self._source_callback is None:
                print("pyshell: source: not available", file=sys.stderr)
                self._set_exit_code(1)
                return None
            path = args[0]
            try:
                self._source_callback(path)
            except SystemExit:
                raise
            except Exception as e:
                print(f"pyshell: source: {e}", file=sys.stderr)
                self._set_exit_code(1)
            else:
                self._set_exit_code(0)
            return None
        if os.name == "nt" and name in ("cat", "echo"):
            try:
                out = run_cat(argv) if name == "cat" else run_echo(argv)
            except OSError as e:
                print(f"pyshell: {name}: {e}", file=sys.stderr)
                self._set_exit_code(1)
                return None
            stdout_f, stderr_f, stdin_f, _ = _apply_redirects(redirects)
            try:
                if stdout_f is not None and stdout_f != sys.stdout:
                    stdout_f.write(out)
                else:
                    self._set_exit_code(0)
                    return out
            finally:
                if stdout_f is not None and stdout_f != sys.stdout:
                    stdout_f.close()
                if stderr_f is not None and stderr_f != sys.stderr:
                    stderr_f.close()
                if stdin_f is not None and stdin_f != sys.stdin:
                    stdin_f.close()
            self._set_exit_code(0)
            return None
        if os.name == "nt" and name in ("ls", "dir"):
            try:
                out = run_ls_dir(argv)
            except OSError as e:
                print(f"pyshell: {name}: {e}", file=sys.stderr)
                self._set_exit_code(1)
                return None
            stdout_f, stderr_f, stdin_f, _ = _apply_redirects(redirects)
            try:
                if stdout_f is not None and stdout_f != sys.stdout:
                    stdout_f.write(out)
                    if not out.endswith("\n"):
                        stdout_f.write("\n")
                else:
                    self._set_exit_code(0)
                    return out
            finally:
                if stdout_f is not None and stdout_f != sys.stdout:
                    stdout_f.close()
                if stderr_f is not None and stderr_f != sys.stderr:
                    stderr_f.close()
                if stdin_f is not None and stdin_f != sys.stdin:
                    stdin_f.close()
            self._set_exit_code(0)
            return None
        try:
            result = run_builtin_command(name, args)
        except SystemExit:
            raise
        if result is not None:
            self._set_exit_code(0)
            if result != "":
                return result
            return None
        argv = _resolve_command_argv(argv)
        if argv is None:
            self._set_exit_code(127)
            print(f"pyshell: command not found: {name}", file=sys.stderr)
            return None
        stdout_f, stderr_f, stdin_f, stderr_to_stdout = _apply_redirects(redirects)
        try:
            if background:
                proc = subprocess.Popen(
                    argv,
                    shell=False,
                    env=os.environ,
                    stdout=stdout_f or subprocess.DEVNULL,
                    stderr=stderr_f if not stderr_to_stdout else subprocess.STDOUT,
                    stdin=stdin_f or subprocess.DEVNULL,
                    start_new_session=True,
                )
                job_id = self._next_job_id
                self._next_job_id += 1
                self._jobs.append({"id": job_id, "procs": [proc], "cmd": " ".join(argv)})
                print(f"[{job_id}] {proc.pid}")
                self._set_exit_code(0)
                return None
            out_target = stdout_f or sys.stdout
            err_target = stderr_f if not stderr_to_stdout else sys.stderr
            use_pipe_stdout = stdout_f is None and not _has_fileno(sys.stdout)
            use_pipe_stderr = (
                not stderr_to_stdout
                and (stderr_f is None and not _has_fileno(sys.stderr))
            )
            try:
                proc = subprocess.run(
                    argv,
                    shell=False,
                    env=os.environ,
                    stdout=subprocess.PIPE if use_pipe_stdout else out_target,
                    stderr=subprocess.STDOUT if stderr_to_stdout else (
                        subprocess.PIPE if use_pipe_stderr else err_target
                    ),
                    stdin=stdin_f or _safe_stdin(),
                    text=True,
                )
                if use_pipe_stdout and proc.stdout:
                    sys.stdout.write(proc.stdout)
                if use_pipe_stderr and proc.stderr:
                    sys.stderr.write(proc.stderr)
                self._set_exit_code(proc.returncode if proc.returncode is not None else 0)
            except KeyboardInterrupt:
                self._set_exit_code(130)
                raise
        except FileNotFoundError:
            self._set_exit_code(127)
            print(f"pyshell: command not found: {name}", file=sys.stderr)
            return None
        except PermissionError:
            self._set_exit_code(126)
            print(f"pyshell: permission denied: {name}", file=sys.stderr)
            return None
        finally:
            if stdout_f is not None and stdout_f != sys.stdout:
                stdout_f.close()
            if stderr_f is not None and stderr_f != sys.stderr:
                stderr_f.close()
            if stdin_f is not None and stdin_f != sys.stdin:
                stdin_f.close()
        return None

    def run_pipeline(
        self,
        segments: list[list[str]],
        redirects: Redirects | None = None,
        background: bool = False,
    ) -> Any:
        """Run a pipeline of commands (cmd1 | cmd2 | ...). Returns last command's output or None."""
        redirects = redirects or []
        if not segments:
            self._set_exit_code(0)
            return None
        if len(segments) == 1:
            return self.run_command(segments[0], redirects=redirects, background=background)
        env = self._get_namespace()
        stdout_f, stderr_f, stdin_f, stderr_to_stdout = _apply_redirects(redirects)
        out_target = stdout_f or sys.stdout
        # When capturing (command substitution uses a pipe, not the real stdout), don't pass sys.stderr to Popen (Windows can close it).
        capturing = out_target is not getattr(sys, "__stdout__", sys.stdout) or not _has_fileno(out_target)
        try:
            last_stdout: str | None = None
            last_code = 0
            for i, argv in enumerate(segments):
                if not argv:
                    continue
                argv = expand_command_argv(argv, env)
                name, args = argv[0], argv[1:]
                try:
                    result = run_builtin_command(name, args)
                except SystemExit:
                    raise
                if result is not None:
                    out = (result if isinstance(result, str) else "") or ""
                    last_stdout = out
                    last_code = 0
                    continue
                resolved = _resolve_command_argv(argv)
                if resolved is None:
                    last_code = 127
                    self._set_exit_code(127)
                    print(f"pyshell: command not found: {name}", file=sys.stderr)
                    break
                is_first = i == 0
                is_last = i == len(segments) - 1
                out_target = stdout_f or sys.stdout
                use_pipe_for_last = is_last and not _has_fileno(out_target)
                proc_stdin: Any = None
                if is_first and stdin_f is not None:
                    proc_stdin = stdin_f
                elif last_stdout is not None:
                    proc_stdin = subprocess.PIPE
                elif proc_stdin is None:
                    proc_stdin = subprocess.DEVNULL if (capturing and is_first) else _safe_stdin()
                # When passing our capture pipe to the last stage, pass a duplicate fd so
                # communicate() does not close the original (which is sys.stdout in _run_and_capture).
                if is_last and not use_pipe_for_last and capturing:
                    dup_fd = os.dup(out_target.fileno())
                    proc_stdout = open(
                        dup_fd, "w", encoding=getattr(out_target, "encoding", None) or "utf-8"
                    )
                    close_proc_stdout = True
                else:
                    proc_stdout = (
                        subprocess.PIPE
                        if (not is_last or use_pipe_for_last)
                        else out_target
                    )
                    close_proc_stdout = False
                if capturing:
                    proc_stderr = subprocess.PIPE
                elif not stderr_to_stdout:
                    proc_stderr = sys.stderr
                    if is_last and stderr_f is not None:
                        proc_stderr = stderr_f
                else:
                    proc_stderr = subprocess.STDOUT
                try:
                    proc = subprocess.Popen(
                        resolved,
                        stdin=proc_stdin,
                        stdout=proc_stdout,
                        stderr=proc_stderr,
                        env=os.environ,
                        text=True,
                    )
                    if last_stdout is not None and proc_stdin == subprocess.PIPE:
                        proc.stdin.write(last_stdout)  # type: ignore
                        # Do not close stdin here: communicate() flushes then closes it; closing first causes "I/O operation on closed file" on Linux.
                    if is_first and stdin_f is not None and proc_stdin is stdin_f:
                        pass  # stdin is the file, not PIPE
                    try:
                        out, err = proc.communicate()
                    finally:
                        if close_proc_stdout:
                            proc_stdout.close()
                    if capturing and err:
                        try:
                            sys.stderr.write(err)
                            sys.stderr.flush()
                        except OSError:
                            pass  # e.g. stderr closed on Windows when capturing
                    last_stdout = out or ""
                    if use_pipe_for_last and last_stdout:
                        out_target.write(last_stdout)
                        if hasattr(out_target, "flush"):
                            out_target.flush()
                    last_code = proc.returncode if proc.returncode is not None else 0
                except FileNotFoundError:
                    last_code = 127
                    self._set_exit_code(127)
                    print(f"pyshell: command not found: {name}", file=sys.stderr)
                    break
                except KeyboardInterrupt:
                    last_code = 130
                    self._set_exit_code(130)
                    raise
            self._set_exit_code(last_code)
            return None
        except KeyboardInterrupt:
            self._set_exit_code(130)
            raise
        finally:
            if stdout_f is not None and stdout_f != sys.stdout:
                stdout_f.close()
            if stderr_f is not None and stderr_f != sys.stderr:
                stderr_f.close()
            if stdin_f is not None and stdin_f != sys.stdin:
                stdin_f.close()


def _safe_stdin() -> Any:
    """Return stdin for subprocess; use DEVNULL if sys.stdin has no fileno (e.g. under pytest)."""
    try:
        sys.stdin.fileno()
        return sys.stdin
    except (OSError, AttributeError):
        return subprocess.DEVNULL


def _has_fileno(stream: Any) -> bool:
    try:
        stream.fileno()
        return True
    except (OSError, AttributeError):
        return False


def _apply_redirects(redirects: Redirects) -> tuple[Any, Any, Any, bool]:
    """Apply redirect list. Returns (stdout_file, stderr_file, stdin_file, stderr_to_stdout)."""
    stdout_f: Any = None
    stderr_f: Any = None
    stdin_f: Any = None
    stderr_to_stdout = False
    for op, path in redirects:
        if op == ">":
            stdout_f = open(path, "w", encoding="utf-8")
        elif op == ">>":
            stdout_f = open(path, "a", encoding="utf-8")
        elif op == "<":
            stdin_f = open(path, "r", encoding="utf-8")
        elif op == "2>":
            stderr_f = open(path, "w", encoding="utf-8")
        elif op == "2>>":
            stderr_f = open(path, "a", encoding="utf-8")
        elif op == "2>&1":
            stderr_to_stdout = True
    return (stdout_f, stderr_f, stdin_f, stderr_to_stdout)


def _run_builtin_jobs(jobs: list) -> None:
    for j in jobs:
        procs = j.get("procs", [])
        pid = procs[0].pid if procs else "?"
        status = "running" if (procs and procs[0].poll() is None) else "done"
        print(f"[{j['id']}] {pid} {status} {j.get('cmd', '')}")


def _run_builtin_fg(jobs: list, set_exit_code: Any) -> None:
    if not jobs:
        print("pyshell: fg: no current job", file=sys.stderr)
        set_exit_code(1)
        return
    job = jobs.pop()
    procs = job.get("procs", [])
    for p in procs:
        try:
            p.wait()
            set_exit_code(p.returncode if p.returncode is not None else 0)
        except Exception:
            pass


def _run_builtin_bg(jobs: list) -> None:
    for j in jobs:
        for p in j.get("procs", []):
            if p.poll() is None:
                pass  # already running; no op for bg on running job


def _is_expression_statement(tree: ast.AST) -> bool:
    """True if the module is a single expression (e.g. 2+3 or f())."""
    if not isinstance(tree, ast.Module):
        return False
    if len(tree.body) != 1:
        return False
    node = tree.body[0]
    return isinstance(node, ast.Expr)


def _is_bare_name(tree: ast.AST) -> bool:
    """True if the expression is a single identifier (e.g. pwd, foo)."""
    return isinstance(tree, ast.Name)


def _resolve_command_argv(argv: list[str]) -> list[str] | None:
    """Resolve the first token via PATH; return new argv or None if not found."""
    if not argv:
        return argv
    name = argv[0]
    # Already an absolute path or has path separators
    if os.path.isabs(name) or os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return argv if os.path.isfile(name) or os.path.isfile(name + ".exe") else None
    path = os.environ.get("PATH", "")
    resolved = shutil.which(name, path=path)
    if resolved is None:
        return None
    return [resolved] + argv[1:]
