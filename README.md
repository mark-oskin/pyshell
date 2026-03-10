# pyshell

A command-line shell written in Python with **Python-like syntax**. Use Python expressions and statements interactively, or run external commands the same way you would in a traditional shell.

## Features

- **Python syntax**: Assign variables, evaluate expressions, call functions, use `print()`, etc.
- **Shell commands**: Type a command and arguments (e.g. `ls -la`, `git status`); if it isn’t valid Python, it’s run as an external program.
- **Line continuation**: End a line with `\` to continue on the next line.
- **Built-in commands**: `cd`, `pwd`, `exit`, `env`, `alias`, `unalias`, `jobs`, `fg`, `bg`, `help` (as commands or from Python). You can type `pwd` or `pwd()` — both work.
- **PATH**: External commands (e.g. `ls`) are resolved using your `PATH`, including on Windows (e.g. Git Bash `ls`).
- **Aliases**: `alias ll='ls -la'` then type `ll`; `unalias ll` to remove. Use `alias` with no args to list.
- **Redirects**: `> file`, `>> file`, `< file`, `2> err`, `2>> err`, `2>&1` (e.g. `echo hi > out.txt`).
- **Background jobs**: End a command with `&` to run in background; `jobs` to list, `fg` to bring last job to foreground.
- **Custom prompt**: `prompt(">>> ")` or `prompt("{base} $ ")`; use `{cwd}` and `{base}` for the current directory.
- **Tab completion**: Commands (builtins + PATH), filenames, and variables (when readline is available).
- **Pipelines**: `cmd1 | cmd2` (e.g. `pwd | cat`). **History** and **last exit code** (`last_exit_code`). **Scripts**: `pyshell script.psh`.
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
Use `{cwd}` for the full current path and `{base}` for its last component. Call `prompt()` with no arguments to restore the default.

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

Example script that uses several of these:

```text
# in script.psh or at the prompt
cd("~/projects")
out, err, code = run_capture("git", "status")
if code != 0:
    print("git failed:", err)
    exit(1)
print(out)
```

## Requirements

- Python 3.10+

## License

MIT
