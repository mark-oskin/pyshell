"""Shell built-in commands and Python-builtin helpers."""

import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from pyshell.shell import Shell

# One-line description for every builtin (shell command or Python callable)
BUILTIN_HELP: dict[str, str] = {
    "alias": "List or define command aliases. alias, alias name=value, alias name",
    "bg": "Resume a background job.",
    "cd": "Change current directory. No args = home.",
    "dirs": "Print the directory stack (cwd and pushd stack).",
    "env": "Print environment variables.",
    "exit": "Exit the shell with an optional code.",
    "fg": "Bring a background job to the foreground.",
    "help": "List builtins or show help for a builtin. help [topic]",
    "history": "Show command history.",
    "jobs": "List background jobs.",
    "popd": "Pop directory from stack and cd to it.",
    "prompt": "Set the REPL prompt. Use {cwd}, {base}. prompt() = default.",
    "pushd": "Push cwd onto stack and cd to dir; no arg = swap cwd with top.",
    "pwd": "Print working directory.",
    "run": "Run an external command from Python. run(cmd, *args) -> exit code.",
    "run_capture": "Run command and return (stdout, stderr, returncode).",
    "source": "Run a script in the current shell. source file or . file",
    "type": "Show whether a name is an alias, builtin, or path. type name [...]",
    "unalias": "Remove an alias. unalias name",
    "which": "Print path or builtin/alias for a command. which name [...]",
}


def make_builtins(
    exit_callback: Callable[[int], None],
    get_history: Callable[[], list[str]] | None = None,
    aliases: dict[str, str] | None = None,
    set_prompt: Callable[[str | None], None] | None = None,
) -> dict[str, Any]:
    """Build the namespace of shell builtins (for Python execution and commands)."""
    _aliases = aliases if aliases is not None else {}

    def cd(path: str = "") -> None:
        """Change current directory. No args = go to home."""
        if path:
            os.chdir(path)
        else:
            os.chdir(os.path.expanduser("~"))

    def pwd() -> str:
        """Return current working directory."""
        return os.getcwd()

    def exit(code: int = 0) -> None:
        """Exit the shell with the given code."""
        exit_callback(code)

    def env() -> dict[str, str]:
        """Return current environment as a dict (copy)."""
        return dict(os.environ)

    def run(*args: str) -> int:
        """Run an external command. Returns exit code. E.g. run('ls', '-la')."""
        if not args:
            print("run(cmd, *args): at least one argument required", file=sys.stderr)
            return 1
        result = subprocess.run(list(args))
        return result.returncode

    def run_capture(*args: str) -> tuple[str, str, int]:
        """Run command and return (stdout, stderr, returncode)."""
        if not args:
            return ("", "run_capture(cmd, *args): at least one argument required", 1)
        r = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
        )
        return (r.stdout or "", r.stderr or "", r.returncode)

    def history() -> list[str]:
        """Return the list of previously executed lines (command history)."""
        return list(get_history()) if get_history else []

    def alias(name: str | None = None, value: str | None = None) -> dict[str, str] | None:
        """alias() -> all aliases; alias('ll', 'ls -la') -> set; alias('ll') -> get value."""
        if name is None:
            return dict(_aliases)
        if value is None:
            return _aliases.get(name)
        _aliases[name] = value
        return None

    def unalias(name: str) -> None:
        """Remove an alias."""
        _aliases.pop(name, None)

    def prompt(s: str | None = None) -> None:
        """Set the REPL prompt. Use {cwd} and {base} for current dir. prompt() or prompt(None) = default."""
        if set_prompt:
            set_prompt(s)

    def help(topic: str = "") -> str:
        """Show help for builtins. help() or help('cd')."""
        if not topic:
            lines = ["Builtins (use help('name') for details):"]
            for name in sorted(BUILTIN_HELP.keys()):
                lines.append(f"  {name:<12} {BUILTIN_HELP[name]}")
            lines.append("")
            lines.append("Python: assignments, expressions, print(), etc. External commands: type name and args.")
            return "\n".join(lines)
        if topic in BUILTIN_HELP:
            fn = {"cd": cd, "pwd": pwd, "exit": exit, "env": env, "run": run, "run_capture": run_capture, "history": history, "alias": alias, "unalias": unalias, "prompt": prompt, "help": help}.get(topic)
            return (fn.__doc__ or BUILTIN_HELP[topic]).strip()
        return f"Unknown builtin: {topic!r}"

    return {
        "cd": cd,
        "pwd": pwd,
        "exit": exit,
        "env": env,
        "run": run,
        "run_capture": run_capture,
        "history": history,
        "alias": alias,
        "unalias": unalias,
        "prompt": prompt,
        "help": help,
    }


def run_builtin_command(name: str, args: list[str]) -> str | int | None:
    """
    Run a builtin by name with string args. Returns output string or exit code.
    Returns None if not a builtin (caller should run external command).
    """
    if name == "cd":
        path = args[0] if args else ""
        if path:
            os.chdir(path)
        else:
            os.chdir(os.path.expanduser("~"))
        return ""

    if name == "pwd":
        return os.getcwd()

    if name == "exit":
        code = int(args[0]) if args else 0
        raise SystemExit(code)

    if name == "env":
        for k, v in sorted(os.environ.items()):
            print(f"{k}={v}")
        return ""

    if name == "help":
        if not args:
            for name in sorted(BUILTIN_HELP.keys()):
                print(f"  {name:<12} {BUILTIN_HELP[name]}")
            print("\nUse help(name) for details. Python: expressions, print(), etc. Commands: name and args.")
        else:
            topic = args[0]
            if topic in BUILTIN_HELP:
                print(BUILTIN_HELP[topic])
            else:
                print(f"Unknown builtin: {topic!r}", file=sys.stderr)
        return ""

    return None
