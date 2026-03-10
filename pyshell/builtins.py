"""Shell built-in commands and Python-builtin helpers."""

import os
import subprocess
import sys
from datetime import datetime
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
    "prompt": "Set the REPL prompt. Use {cwd}, {base}, {user}, {hostname}, {time}, {exit}, {jobs}. prompt() = default.",
    "pushd": "Push cwd onto stack and cd to dir; no arg = swap cwd with top.",
    "pwd": "Print working directory.",
    "run": "Run an external command from Python. run(cmd, *args) -> exit code.",
    "run_capture": "Run command and return (stdout, stderr, returncode).",
    "source": "Run a script in the current shell. source file or . file",
    "type": "Show whether a name is an alias, builtin, or path. type name [...]",
    "unalias": "Remove an alias. unalias name",
    "which": "Print path or builtin/alias for a command. which name [...]",
}
# Windows-only: ls, dir, cat, echo (Unix uses external)
if os.name == "nt":
    BUILTIN_HELP["dir"] = "List directory contents. dir [path...] [-l] [-a] (Windows builtin)."
    BUILTIN_HELP["ls"] = "List directory contents. ls [path...] [-l] [-a] (Windows builtin)."
    BUILTIN_HELP["cat"] = "Print file contents. cat [file...] (Windows builtin)."
    BUILTIN_HELP["echo"] = "Print arguments. echo [-n] [arg...] (Windows builtin)."

BUILTIN_HELP["true"] = "Do nothing; exit with code 0."
BUILTIN_HELP["false"] = "Do nothing; exit with code 1."
BUILTIN_HELP["mkdir"] = "Create directory. mkdir [-p] path... (creates parents with -p)."

# Extended help for documentation topics (help('prompt'), help('quoting'), help('windows'))
EXTENDED_HELP: dict[str, str] = {
    "prompt": """Prompt placeholders (use in prompt("...") or the prompt command):

  {cwd}      Full path of current directory
  {base}     Last component of current directory (e.g. project name)
  {user}     Username (USER or USERNAME env)
  {hostname} Machine hostname
  {time}     Current time (HH:MM:SS)
  {exit}     Last command exit code
  {jobs}     Number of background jobs

Examples:
  prompt("{base} $ ")
  prompt("[{user}@{hostname} {base}] $ ")
  prompt("[{time}] {cwd} >>> ")
  prompt()   restores the default ([{base}] >>> )""",
    "quoting": """Quoting and expansion in command lines:

  • Double and single quotes group words into one argument; backslash (\\)
    escapes the next character (including newline for line continuation).
  • After splitting, $VAR and ${VAR} are expanded in each argument from the
    environment; ~ and ~user expand to home directories.
  • Redirect paths and here-strings (<<<) also get $VAR and ~ expansion.
  • Use quotes to include spaces or to protect $ and ~ when you want them
    passed literally (e.g. in Python strings use '...' or escape as needed).""",
    "windows": """Windows vs Unix:

  • Line editing: On Unix, readline is used when available (full line editing,
    history, completion). On Windows, if readline is not installed, pyshell
    uses a key-by-key fallback with history (Up/Down), cursor movement
    (Left/Right, Home/End), Ctrl+A/Ctrl+E, and tab completion.
  • History: Command history is saved to ~/.pyshell_history on exit and loaded
    at startup (same path on Windows: your user profile directory).
  • Commands: On Windows, ls, dir, cat, and echo are built in when not on PATH.
    On Unix they are run from PATH. mkdir -p is built in on all platforms.""",
}


def run_mkdir(argv: list[str]) -> bool:
    """Built-in mkdir with -p/--parents: create directories. Returns True if all succeeded."""
    args = argv[1:]
    parents = False
    paths = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-p", "--parents"):
            parents = True
        elif a.startswith("-"):
            pass  # ignore other flags
        else:
            paths.append(a)
        i += 1
    ok = True
    for path in paths:
        path = os.path.expanduser(path)
        try:
            if parents:
                os.makedirs(path, exist_ok=True)
            else:
                os.mkdir(path)
        except OSError as e:
            print(f"mkdir: {path}: {e}", file=sys.stderr)
            ok = False
    return ok


def run_cat(argv: list[str]) -> str:
    """Built-in cat for Windows: print file contents. argv[0] is 'cat'; rest are paths."""
    lines: list[str] = []
    for path in argv[1:] or ["-"]:
        if path == "-":
            lines.append(sys.stdin.read())
            continue
        path = os.path.expanduser(path)
        try:
            with open(path, encoding="utf-8") as f:
                lines.append(f.read())
        except OSError as e:
            print(f"cat: {path}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"cat: {path}: {e}", file=sys.stderr)
    return "".join(lines)


def run_echo(argv: list[str]) -> str:
    """Built-in echo for Windows: print arguments. argv[0] is 'echo'; -n = no trailing newline."""
    args = argv[1:]
    no_newline = False
    if args and args[0] == "-n":
        no_newline = True
        args = args[1:]
    s = " ".join(args)
    return s + ("" if no_newline else "\n")


def run_ls_dir(argv: list[str]) -> str:
    """
    Built-in ls/dir for Windows: list directory contents like Unix ls.
    Supports -l (long), -a/--all (include dotfiles), -1 (one per line).
    argv[0] is the command name (ls or dir); parse argv[1:] for paths and flags.
    Returns the formatted output string.
    """
    paths: list[str] = []
    long_fmt = False
    show_all = False
    one_per_line = False
    args = argv[1:] if len(argv) > 1 else []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("-"):
            for c in a[1:]:
                if c == "l":
                    long_fmt = True
                elif c == "a":
                    show_all = True
                elif c == "1":
                    one_per_line = True
            if a in ("--all", "-all"):
                show_all = True
            i += 1
        else:
            paths.append(a)
            i += 1
    if not paths:
        paths = ["."]
    lines: list[str] = []
    for path in paths:
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            lines.append(f"ls: {path}: No such file or directory")
            continue
        if os.path.isfile(path):
            if long_fmt:
                st = os.stat(path)
                mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                size = st.st_size
                lines.append(f"{size:>12}  {mtime}  {path}")
            else:
                lines.append(path)
            continue
        # Directory
        try:
            entries = []
            with os.scandir(path) as it:
                for e in it:
                    if not show_all and e.name.startswith("."):
                        continue
                    entries.append(e)
        except OSError as err:
            lines.append(f"ls: {path}: {err}")
            continue
        # Sort: directories first, then by name
        def sort_key(ent: os.DirEntry) -> tuple[int, str]:
            return (0 if ent.is_dir() else 1, ent.name.lower())
        entries.sort(key=sort_key)
        if path != "." and (len(paths) > 1 or long_fmt):
            lines.append(f"{path}:")
        if long_fmt or one_per_line:
            for e in entries:
                try:
                    st = e.stat()
                except OSError:
                    st = None
                if long_fmt and st is not None:
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    size = st.st_size if e.is_file() else 0
                    kind = "d" if e.is_dir() else "-"
                    lines.append(f"{kind} {size:>12}  {mtime}  {e.name}")
                else:
                    lines.append(e.name)
        else:
            # Columnar: fit names in ~80 cols (or 4 columns min)
            names = [e.name for e in entries]
            col_width = max(len(n) for n in names) + 2 if names else 0
            try:
                term_width = os.get_terminal_size().columns
            except OSError:
                term_width = 80
            ncols = max(1, term_width // col_width) if col_width else 1
            row = []
            for i, n in enumerate(names):
                row.append(n.ljust(col_width))
                if (i + 1) % ncols == 0 or i == len(names) - 1:
                    lines.append("".join(row).rstrip())
                    row = []
        if path != "." and len(paths) > 1 and entries:
            lines.append("")
    return "\n".join(lines)


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
        """Set the REPL prompt. Placeholders: {cwd}, {base}, {user}, {hostname}, {time}, {exit}, {jobs}. prompt() = default."""
        if set_prompt:
            set_prompt(s)

    def help(topic: str = "") -> str:
        """Show help for builtins. help() or help('cd'). Extended: help('prompt'), help('quoting'), help('windows')."""
        if not topic:
            lines = ["Builtins (use help('name') for details):"]
            for name in sorted(BUILTIN_HELP.keys()):
                lines.append(f"  {name:<12} {BUILTIN_HELP[name]}")
            lines.append("")
            lines.append("Extended docs: help('prompt'), help('quoting'), help('windows')")
            lines.append("")
            lines.append("Python: assignments, expressions, print(), etc. shell.run(cmd), shell.capture(cmd), shell.cd/pwd/pushd/popd/dirs.")
            lines.append("External commands: type name and args.")
            return "\n".join(lines)
        if topic in EXTENDED_HELP:
            return EXTENDED_HELP[topic].strip()
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
            for bname in sorted(BUILTIN_HELP.keys()):
                print(f"  {bname:<12} {BUILTIN_HELP[bname]}")
            print("\nExtended docs: help prompt, help quoting, help windows")
            print("Use help(name) for details. Python: expressions, print(), etc. Commands: name and args.")
        else:
            topic = args[0]
            if topic in EXTENDED_HELP:
                print(EXTENDED_HELP[topic])
            elif topic in BUILTIN_HELP:
                print(BUILTIN_HELP[topic])
            else:
                print(f"Unknown builtin: {topic!r}", file=sys.stderr)
        return ""

    return None
