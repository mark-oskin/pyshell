"""Shell built-in commands and Python-builtin helpers.

Provides run_* implementations for mkdir, cat, echo, ls/dir (Windows),
make_builtins() for the Python namespace, and run_builtin_command() for
shell-invoked builtins. BUILTIN_HELP and EXTENDED_HELP drive the help command.
"""

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

  {cwd}      Full path of current directory (resolved; symlinks show target name)
  {base}     Last component of current directory (e.g. project name; resolved if symlink)
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
    """Create directories; -p/--parents creates parent dirs.

    Args:
        argv: [ "mkdir", "-p"?, path, ... ].

    Returns:
        True if all directories were created or already existed; False on error.
    """
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
    """Print file contents (Windows builtin when cat not on PATH).

    Args:
        argv: [ "cat", path, ... ]. path "-" means stdin.

    Returns:
        Concatenated file contents as a string.
    """
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
    """Print arguments (Windows builtin). -n suppresses trailing newline.

    Args:
        argv: [ "echo", "-n"?, arg, ... ].

    Returns:
        Arguments joined by space, with or without trailing newline.
    """
    args = argv[1:]
    no_newline = False
    if args and args[0] == "-n":
        no_newline = True
        args = args[1:]
    s = " ".join(args)
    return s + ("" if no_newline else "\n")


def _ls_fallback_via_cmd(
    list_path: str,
    show_all: bool,
    long_fmt: bool,
    one_per_line: bool,
    path: str,
    paths: list[str],
    lines: list[str],
) -> bool:
    """On Windows, when Python cannot list the directory (e.g. symlink/junction like
    Application Data, or restricted/hidden entries), run cmd /c dir. Returns True on success.
    """
    try:
        # /a = show all (including hidden/system); default dir hides hidden.
        r = subprocess.run(
            ["cmd", "/c", "dir", "/b", "/a", list_path] if show_all else ["cmd", "/c", "dir", "/b", list_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        return False
    names = [n.strip() for n in r.stdout.splitlines() if n.strip() and n.strip() not in (".", "..")]
    if not show_all:
        names = [n for n in names if not n.startswith(".")]
    if path != "." and (len(paths) > 1 or long_fmt):
        lines.append(f"{path}:")
    if one_per_line or long_fmt:
        for n in names:
            lines.append(n)
    else:
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
    if path != "." and len(paths) > 1 and names:
        lines.append("")
    return True


def run_ls_dir(argv: list[str]) -> str:
    """List directory contents like Unix ls (Windows builtin).

    Args:
        argv: [ "ls"|"dir", path?, -l?, -a|--all?, -1? ]. -l long, -a dotfiles, -1 one per line.

    Returns:
        Formatted listing string.
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
    # When path args were split by the shell (e.g. "ls My Folder" unquoted), join them
    # so a single directory with spaces is listed (same idea as cd/pushd).
    if len(paths) > 1:
        joined = " ".join(paths)
        if os.path.exists(joined):
            paths = [joined]
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
        # Directory: use absolute path for syscalls so Windows can list directories
        # whose path contains spaces or is a special folder (e.g. Application Data).
        list_path = os.path.abspath(path)
        entries: list[os.DirEntry | tuple[str, bool]] = []  # DirEntry or (name, is_dir)
        try:
            with os.scandir(list_path) as it:
                for e in it:
                    if not show_all and e.name.startswith("."):
                        continue
                    entries.append(e)
        except PermissionError:
            try:
                names = os.listdir(list_path)
            except OSError:
                # Python APIs denied: symlink/junction (e.g. Application Data → Roaming) or
                # restricted/hidden entries on Windows. Try system dir as fallback.
                if os.name == "nt" and _ls_fallback_via_cmd(list_path, show_all, long_fmt, one_per_line, path, paths, lines):
                    continue
                lines.append(f"ls: {path}: Permission denied")
                continue
            # Build minimal entries: (name, is_dir) for sorting/display
            for n in names:
                if not show_all and n.startswith("."):
                    continue
                try:
                    full = os.path.join(list_path, n)
                    entries.append((n, os.path.isdir(full)))
                except OSError:
                    entries.append((n, False))
        except OSError as err:
            lines.append(f"ls: {path}: {err}")
            continue
        # Sort: directories first, then by name
        def sort_key(ent: os.DirEntry | tuple[str, bool]) -> tuple[int, str]:
            if isinstance(ent, tuple):
                name, is_dir = ent
                return (0 if is_dir else 1, name.lower())
            return (0 if ent.is_dir() else 1, ent.name.lower())
        entries.sort(key=sort_key)
        if path != "." and (len(paths) > 1 or long_fmt):
            lines.append(f"{path}:")
        def ent_name(ent: os.DirEntry | tuple[str, bool]) -> str:
            return ent[0] if isinstance(ent, tuple) else ent.name
        def ent_isdir(ent: os.DirEntry | tuple[str, bool]) -> bool:
            return ent[1] if isinstance(ent, tuple) else ent.is_dir()
        if long_fmt or one_per_line:
            for e in entries:
                st = None
                if not isinstance(e, tuple):
                    try:
                        st = e.stat()
                    except OSError:
                        pass
                elif long_fmt:
                    try:
                        st = os.stat(os.path.join(list_path, ent_name(e)))
                    except OSError:
                        pass
                if long_fmt and st is not None:
                    mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    size = 0 if ent_isdir(e) else st.st_size
                    kind = "d" if ent_isdir(e) else "-"
                    lines.append(f"{kind} {size:>12}  {mtime}  {ent_name(e)}")
                else:
                    lines.append(ent_name(e))
        else:
            # Columnar: fit names in ~80 cols (or 4 columns min)
            names = [ent_name(e) for e in entries]
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
    """Run a builtin command by name (shell invocation).

    Args:
        name: Command name (e.g. "cd", "help").
        args: List of string arguments.

    Returns:
        Output string, exit code (int), or None if name is not a builtin.
    """
    if name == "cd":
        path = " ".join(args).strip() if args else ""
        if path:
            path = os.path.expanduser(path)
            try:
                os.chdir(path)
            except FileNotFoundError:
                # If relative path not found (e.g. "Application Data" from OneDrive),
                # try under home (e.g. ~/Application Data).
                if os.sep not in path and os.path.altsep not in (path or ""):
                    home_path = os.path.join(os.path.expanduser("~"), path)
                    if os.path.isdir(home_path):
                        os.chdir(home_path)
                    else:
                        raise
                else:
                    raise
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
