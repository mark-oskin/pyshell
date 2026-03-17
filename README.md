# pyshell

A command-line shell written in Python with **Python-like syntax**. Use Python expressions and statements interactively, or run external commands the same way you would in a traditional shell.

## Features

- **Python syntax**: Assign variables, evaluate expressions, call functions, use `print()`, etc.
- **Shell commands**: Type a command and arguments (e.g. `ls -la`, `git status`); if it isn’t valid Python, it’s run as an external program.
- **Line continuation**: End a line with `\` to continue on the next line.
- **Built-in commands**: `cd`, `pwd`, `exit`, `env`, `alias`, `unalias`, `jobs`, `fg`, `bg`, `help` (as commands or from Python). You can type `pwd` or `pwd()` — both work.
- **PATH**: External commands (e.g. `ls`) are resolved using your `PATH`. On **Windows**, `ls`, `dir`, `cat`, and `echo` are built-in (Unix-style) when not on PATH.
- **true / false**: Built-in no-ops that set exit code 0 or 1 (e.g. for `false || echo failed`).
- **mkdir -p**: Built-in `mkdir` supports `-p` / `--parents` to create parent directories on all platforms.
- **Aliases**: `alias ll='ls -la'` then type `ll`; `unalias ll` to remove. Use `alias` with no args to list.
- **Redirects**: `> file`, `>> file`, `< file`, `<<< string` (here-string), `2> err`, `2>> err`, `2>&1` (e.g. `echo hi > out.txt`, `cat <<< "hello"`).
- **Background jobs**: End a command with `&` to run in background; `jobs` to list, `fg` to bring last job to foreground.
- **Custom prompt**: `prompt(">>> ")` or `prompt("{base} $ ")`; placeholders: `{cwd}`, `{base}`, `{user}`, `{hostname}`, `{time}`, `{exit}`, `{jobs}` (see [Prompt placeholders](#prompt-placeholders)).
- **Tab completion**: Commands (builtins + PATH), filenames, and variables (when readline is available).
- **Pipelines**: `cmd1 | cmd2` (e.g. `pwd | cat`). **History** (persistent in `~/.pyshell_history`) and **last exit code** (`last_exit_code`). **Scripts**: `pyshell script.psh`.
- **Startup config**: Put commands or Python in `~/.pyshellrc` or `./.pyshellrc`; they run automatically when the REPL starts.
- **Glob expansion**: Command arguments like `*.py` or `src/**/*.py` are expanded to matching paths.
- **~ expansion**: `~` and `~user` in command arguments expand to home directories (e.g. `cd ~`, `cat ~/.pyshellrc`).
- **$VAR expansion**: In commands, `$HOME`, `${PATH}`, etc. are expanded from the environment (e.g. `echo $PATH`).
- **Subshell**: Wrap a command in parentheses to run it in a new pyshell process: `( cd /tmp && pwd )`. Changes (e.g. `cd`, variables) inside the subshell do not affect the current shell. Distinct from `$( ... )` (command substitution).

## Installation

From the project directory:

```bash
pip install -e .
```

Or run without installing:

```bash
python -m pyshell
```

After install, run:

```bash
pyshell
```

## Usage examples

### Python at the prompt

You can write normal Python: expressions are evaluated and printed, and statements (assignments, loops, etc.) run in a persistent namespace.

```text
>>> 2 + 3
5
>>> 10 ** 2
100
>>> name = "pyshell"
>>> print("Hello,", name)
Hello, pyshell
>>> items = [1, 2, 3]
>>> [x * 2 for x in items]
[2, 4, 6]
>>> d = {"a": 1, "b": 2}
>>> d["a"] + d["b"]
3
```

Conditionals and loops:

```text
>>> x = 42
>>> "big" if x > 10 else "small"
'big'
>>> for i in range(3):
...     print(i * i)
...
0
1
4
>>> n = 0
>>> while n < 3:
...     print(n)
...     n += 1
...
0
1
2
```

Imports and simple functions:

```text
>>> import os
>>> os.path.basename(pwd())
'pyshell'
>>> from pathlib import Path
>>> list(Path(".").glob("*.py"))
[PosixPath('script.py'), ...]   # paths of .py files in cwd
>>> def greet(who):
...     return f"Hi, {who}"
...
>>> greet("world")
'Hi, world'
```

Environment and shell integration (env vars and `last_exit_code` are in the namespace):

```text
>>> print(PATH[:50] + "..." if len(PATH) > 50 else PATH)
/usr/bin:/bin:...
>>> pwd()
'/home/you'
>>> cd /tmp
>>> run("ls")
>>> last_exit_code
0
>>> run_capture("echo", "hi")
('hi\n', '', 0)
>>> out, err, code = run_capture("false")
>>> code
1
```

**Script API**: The `shell` object exposes the same machinery to Python and scripts. Use it for job control and for running commands with full shell parsing (redirects, `&`, etc.):

```text
>>> shell.run("sleep 5", background=True)
0
>>> shell.jobs()
[{'id': 1, 'cmd': 'sleep 5', 'status': 'running', 'pid': 12345}]
>>> shell.fg()                    # bring job to foreground; blocks until it finishes
>>> shell.run("sleep 10 &")
>>> shell.kill("%1")              # or shell.kill("-9", "%1")
>>> shell.exit_code()
0
>>> shell.prompt("{base} $ ")
```

In the REPL, run `help('shell')` for the full script API (run, capture, jobs, fg, bg, kill, exit_code, prompt, cd, pwd, pushd, popd, dirs).

Line continuation with `\` lets you split long lines:

```text
>>> total = 1 + 2 + 3 + \
...     4 + 5
>>> total
15
>>> exit()
```

### Shell commands

Run external commands by typing them as you would in bash (no commas, no quotes unless needed):

```text
>>> ls -la
>>> git status
>>> alias ll='ls -la'
>>> ll
>>> echo hello > /tmp/out.txt
>>> echo $HOME
/home/you
>>> cd ~
>>> ls *.py
>>> python -c "import time; time.sleep(2)" &
[1] 12345
>>> jobs
>>> fg
```

Create `~/.pyshellrc` or `./.pyshellrc` to run commands at startup (e.g. set aliases, variables).

### Custom prompt

Set the REPL prompt with `prompt(...)` in Python or the `prompt` command:

```text
>>> prompt(">>> ")
>>> prompt("{base} $ ")
pyshell $
>>> prompt("[{cwd}] >>> ")
[/home/you/projects] >>>
>>> prompt()
```

Call `prompt()` with no arguments to restore the default. In the shell: `help prompt` or `help('prompt')` for full details.

#### Prompt placeholders

| Placeholder  | Description |
|-------------|-------------|
| `{cwd}`     | Full path of current directory |
| `{base}`    | Last component of current directory (e.g. project name) |
| `{user}`    | Username (`USER` or `USERNAME` env) |
| `{hostname}`| Machine hostname |
| `{time}`    | Current time (HH:MM:SS) |
| `{exit}`    | Last command exit code |
| `{jobs}`    | Number of background jobs |

Examples: `prompt("{user}@{hostname} {base} $ ")`, `prompt("[{time}] >>> ")`.

### Quoting

- **Double and single quotes** group words into one argument; use them to include spaces or special characters in a command argument.
- **Backslash** (`\`) escapes the next character (including newline for line continuation).
- **Expansion**: After splitting the line, `$VAR` and `${VAR}` are replaced from the environment, and `~` / `~user` expand to home directories. This applies to command arguments and to redirect paths (including here-strings).
- In the shell, run `help quoting` or `help('quoting')` for a short reference.

### Windows vs Unix

- **Line editing**: On Unix, pyshell uses **readline** when available (full line editing, history keys, completion). On Windows, if readline is not installed, a key-by-key **fallback** is used: Up/Down for history, Left/Right and Home/End for cursor movement, Ctrl+A / Ctrl+E for start/end of line, and Tab for completion.
- **History**: Command history is saved to `~/.pyshell_history` on exit and loaded at startup (on Windows, `~` is your user profile directory). The last 2000 entries are kept.
- **Commands**: On Windows, `ls`, `dir`, `cat`, and `echo` are built in when not on PATH. On Unix they are run from PATH. `mkdir -p` is built in on all platforms.

Run `help windows` or `help('windows')` in the shell for a short summary.

### Builtins and variables for scripts

In Python at the prompt or in `.pyshellrc` / script files, these are available in the namespace:

| Name | Description |
|------|-------------|
| `run(cmd, *args)` | Run an external command; returns exit code (e.g. `run('ls', '-la')`). |
| `run_capture(cmd, *args)` | Run a command and return `(stdout, stderr, returncode)` (e.g. `out, err, code = run_capture('git', 'status')`). |
| `cd(path)` | Change current directory; no args = home. `path` supports `~`. |
| `pwd()` | Return current working directory as a string. |
| `exit(code=0)` | Exit the shell with the given code. |
| `env()` | Return the environment as a dict (copy of `os.environ`). |
| `history()` | Return the list of previously executed input lines. |
| `alias()`, `alias(name, value)`, `unalias(name)` | List aliases, set one, or remove one. |
| `prompt(s)` | Set the REPL prompt; use `{cwd}` and `{base}` for current dir. `prompt()` = default. |
| `help()`, `help('name')` | Short help for builtins. |
| `last_exit_code` | Exit code of the last run command (0 on success, etc.). |
| `PATH`, `HOME`, … | All environment variables are in the namespace (e.g. `print(PATH)`). |
| `shell` | Helper object: `run()`, `capture()`, `jobs()`, `fg()`, `bg()`, `kill()`, `exit_code()`, `prompt()`, `cd()`, `pwd()`, `pushd()`, `popd()`, `dirs()` (see below). Run `help('shell')` for the full script API. |

### Accessing shell functions from Python

You can call shell-related behavior from Python code in two ways: **direct builtins** (same namespace as the REPL) and the **`shell`** helper object. Both work at the prompt and in script files.

#### Direct builtins (function calls)

Use `run`, `run_capture`, `cd`, `pwd`, etc. as normal Python functions. Arguments are passed as separate strings; no shell parsing (so no pipelines or redirects from these calls).

```text
>>> cd("~/projects")
>>> pwd()
'/home/you/projects'
>>> run("ls", "-la")           # exit code goes to last_exit_code
>>> last_exit_code
0
>>> out, err, code = run_capture("git", "status")
>>> code
0
>>> print(out.strip()[:80])
On branch main...
>>> run_capture("echo", "hello")
('hello\n', '', 0)
```

Change directory and run a command from Python:

```text
>>> cd("/tmp")
>>> run("pwd")                 # runs in same shell; output goes to terminal
>>> pwd()
'/tmp'
```

Exit code and environment:

```text
>>> run("false")
>>> last_exit_code
1
>>> "HOME" in env()
True
>>> env()["USER"]
'you'
```

#### The `shell` object (full command lines)

The name **`shell`** in the namespace is a helper that lets you run **entire command lines** as strings (so pipelines, redirects, and shell syntax are interpreted). Useful when you want to pass a single string or build commands dynamically.

| Method | Description |
|--------|-------------|
| `shell.run(cmd, background=False)` | Run one command line. Returns exit code. Use `background=True` to run in background (adds to job list). |
| `shell.capture(cmd)` | Run command line and capture stdout. Returns `(output_string, exit_code)`. |
| `shell.jobs()` | List of jobs: each dict has `id`, `cmd`, `status` ('running'\|'stopped'\|'done'), `pid`. |
| `shell.fg(spec=None)` | Bring job to foreground; blocks until it finishes. `spec` is `None` (most recent) or `'%1'`, etc. |
| `shell.bg(spec=None)` | Resume a stopped job in the background. |
| `shell.kill(*args)` | Send signal to process or job. E.g. `shell.kill('%1')`, `shell.kill('-9', '%1')`. |
| `shell.exit_code()` | Exit code of the last command or pipeline. |
| `shell.prompt(template=None)` | Get current prompt, or set it (e.g. `shell.prompt('{base} $ ')`). |
| `shell.cd(path)` | Change directory; no args = home. |
| `shell.pwd()` | Current working directory. |
| `shell.pushd(path)` | Push cwd onto stack, cd to path; no path = swap with top. |
| `shell.popd()` | Pop directory from stack and cd to it. |
| `shell.dirs()` | Directory stack as a single string (cwd first). |

Examples:

```text
>>> shell.run("ls -la")        # full line; returns exit code
0
>>> out, code = shell.capture("git rev-parse --short HEAD")
>>> out.strip()
'a1b2c3d'
>>> shell.run("echo hello > /tmp/out.txt")
0
>>> shell.capture("cat /tmp/out.txt")
('hello\n', 0)
>>> shell.run("pwd | cat")     # pipeline
0
>>> shell.cd("/tmp")
>>> shell.pwd()
'/tmp'
>>> shell.pushd("/var")
>>> shell.dirs()
'/var /tmp'
>>> shell.popd()
>>> shell.pwd()
'/tmp'
```

#### When to use which

- **`run(cmd, arg1, ...)` / `run_capture(cmd, arg1, ...)`** — You have the command and args as separate values; no need for shell parsing. No pipelines or redirects in the call.
- **`shell.run(cmd)` / `shell.capture(cmd)`** — You have a single command string (e.g. from user input or a config); pipelines and redirects work. Same shell environment (cwd, vars) as the rest of your Python.

Example script that uses both styles:

```text
# in script.psh or at the prompt
cd("~/projects")
out, err, code = run_capture("git", "status")
if code != 0:
    print("git failed:", err)
    exit(1)
print(out)
# run a full line (e.g. with pipe) from a variable
cmd = "git log -1 --oneline"
summary, code = shell.capture(cmd)
print("Last commit:", summary.strip())
```

## Requirements

- Python 3.10+

## License

MIT
