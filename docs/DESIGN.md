# pyshell design document

This document describes the architecture, data flow, and key design decisions for pyshell. It should be updated when behavior or structure changes significantly.

---

## 1. Overview

pyshell is a command-line shell that accepts both **Python-like code** and **shell-style commands**. The REPL classifies each input line as Python or shell (command/pipeline), then either executes it in a persistent Python namespace or runs it as external commands with redirects, pipelines, and conditionals.

**Design principle**: Prefer Python semantics where the line is valid Python; otherwise treat as shell. Users can mix both in the same session.

---

## 2. Architecture

### 2.1 Module roles

| Module | Role |
|--------|------|
| **shell** | Entry point (`main`), REPL loop (`Shell`), line reading (readline vs Windows fallback), history load/save, startup config (`.pyshellrc`), and orchestration: parses line → dispatches to executor. |
| **parser** | Classify line (Python vs command vs pipeline vs conditional), split pipelines and conditionals, tokenize command lines and extract redirects/background. No execution. |
| **executor** | Run Python (`run_python`), run builtins and external commands (`run_command`), run pipelines (`run_pipeline`), apply redirects, manage namespace, aliases, jobs, prompt, directory stack. |
| **builtins** | Implementations of built-in commands (mkdir, cat, echo, ls/dir on Windows) and factory for Python-callable builtins (cd, pwd, run, help, etc.). |
| **expansion** | Expand `$VAR`/`${VAR}` and `~` in strings; glob expansion for argv. Used by executor before running commands and for redirect paths. |

### 2.2 Data flow (single line)

1. **shell**: User input → `_read_line()` (readline or Windows fallback) → optional continuation until line complete.
2. **shell**: `_eval(line)` → if conditional (`&&`/`||`), split and evaluate segments; else `_eval_one(cmd_line, redirects, background)`.
3. **shell**: `_eval_one` uses **parser**: `parse_line(line)` → `("python" \| "command" \| "pipeline", payload)`. If the line has unquoted redirects/background, **parser** `parse_redirects(line)` yields `(argv, redirects, background)`; otherwise line may be run as Python.
4. **executor**: For Python: `run_python(source, line)` (AST parse, eval/exec in namespace). For command: `run_command(argv, redirects, background)`. For pipeline: `run_pipeline(segments, redirects, background)`.
5. **executor**: Commands: expand argv and redirect paths (expansion), resolve builtins vs PATH, apply redirects (`_apply_redirects`), run subprocess or builtin; set `_last_exit_code`.
6. **shell**: Result printed if non-empty; line added to history; loop continues.

### 2.3 Key types

- **Redirects**: `list[tuple[str, str | None]]` — e.g. `[(">", "file"), ("<<<", "string")]`. Ops: `>`, `>>`, `<`, `<<<`, `2>`, `2>>`, `2>&1`.
- **Namespace**: Single dict shared for Python execution; updated with env vars, `last_exit_code`, and `shell` helper; builtins injected on first use.

---

## 3. Parsing and classification

### 3.1 Python vs shell

- Lines with unquoted `|` (pipeline) or unquoted redirect/`&` are treated as shell; the parser never runs them as Python.
- Otherwise: if the line is a **single identifier** (e.g. `pwd`, `ls`) or multiple tokens starting with an identifier without `=` or `(`, it is treated as a command.
- If the line parses as valid Python (AST), it is run as Python; else it is run as a command. So `2 + 3` → Python, `ls -la` → command.

### 3.2 Tokenization

- **parser._split_command**: Splits by spaces; respects double/single quotes and backslash escape. Used for command words and for input to redirect parsing.
- **parser.parse_redirects**: Consumes tokens from `_split_command`; builds argv, list of `(op, path)` redirects, and trailing `&` flag. Here-string `<<<` takes the next token as the string content.

### 3.3 Conditionals and pipelines

- **parser.has_conditional** / **split_conditional**: Split by unquoted `&&` and `||`; segments are evaluated in order; connectors short-circuit.
- **parser._split_pipeline**: Split by unquoted `|`; each segment is a command line. Executor runs stages in a pipeline with pipes between them.

---

## 4. Execution

### 4.1 Python execution

- **executor.run_python**: Parse with `ast.parse`; if single expression, compile as eval and run; bare callable names (e.g. `pwd`) are called. Otherwise exec in namespace.
- Namespace is built by `_get_namespace()`: env vars, builtins (via **builtins.make_builtins**), `last_exit_code`, `shell` (ShellHelper).

### 4.2 Commands

- **executor.run_command**: Expand argv and redirect paths (expansion module); then: builtins (type, which, cd, pwd, exit, alias, jobs, fg, bg, prompt, pushd, popd, dirs, source, history, true, false, mkdir, and on Windows ls/dir/cat/echo) are handled inline; else **builtins.run_builtin_command** for Python-callable builtins; else resolve command via PATH and run subprocess. Redirects applied by `_apply_redirects` (files or here-string pipe for `<<<`). **cd** and **pushd** treat all arguments as a single path (joined by spaces) so directories with spaces work whether quoted or not. **get_prompt** returns the prompt with placeholders expanded; paths (cwd, base) use normal space and come from `os.getcwd()` (symlinks are resolved, so the prompt shows the target directory name). The shell **always** uses the **fallback** line reader for the main prompt: it writes the full prompt with `sys.stdout.write` then calls `input()` with no argument, so readline never receives the prompt and cannot truncate it (GNU readline on Linux/WSL truncates the prompt at the first space).

### 4.3 Redirects

- **executor._apply_redirects**: Opens files for `>`, `>>`, `<`, `2>`, `2>>`; for `<<<` creates a pipe, writes string + newline, passes read end as stdin; `2>&1` sets stderr_to_stdout. Caller attaches these to subprocess or builtin output.

### 4.4 Pipelines and jobs

- **executor.run_pipeline**: Runs each segment as a subprocess; connects stdout of stage N to stdin of stage N+1; redirects apply to the last stage only. Background: `&` runs the (single) command or last pipeline stage in a new process group; **executor** tracks jobs for `jobs`/`fg`/`bg`.

---

## 5. Line reading and history

### 5.1 REPL loop

- **shell.Shell.run**: Load history from `~/.pyshell_history`, then loop: `_read_line()` → strip → `_add_history` → `_eval` → print result. On exit, save history in `finally`.

### 5.2 Line reading

- If **readline** is available: `input(prompt)` with completion and history from readline.
- Else on Windows: **shell._read_line_fallback**: key-by-key with `msvcrt.getwch()`; maintains `line` and cursor `pos`; handles Enter, Ctrl+C, Ctrl+Z, Up/Down (history), Left/Right, Home/End, Ctrl+A/Ctrl+E, Backspace, Tab (completion), and printable insert. No readline dependency.

### 5.3 History persistence

- **shell._load_history** / **_save_history**: File `~/.pyshell_history`; format one logical line per line in file; newlines/backslashes escaped (`\n`, `\\`). Max 2000 entries; load at startup, save on REPL exit.

---

## 6. Startup and configuration

- **main()**: Parses argv for `-c`, `-h`, `--no-rc`, `-v`, script path. Creates **Shell**, wires callbacks (exit, history, shell helper), then either runs `-c` command, script file, or **Shell.run()**.
- **Shell.run**: Registers completion if readline present; runs **Shell._run_startup_config** (`.pyshellrc` from cwd or home); prints banner; loads history; runs main loop; saves history on exit.
- **Shell._run_file_in_current_shell** (used by source/.): Runs file in same namespace, line-by-line with continuation; used for `.pyshellrc` and `source file`.

---

## 7. Platform behavior

- **Windows**: If readline not available, `_read_line_fallback` is used. Builtins `ls`, `dir`, `cat`, `echo` are implemented in **builtins** so they work without PATH. `~` and PATH resolution use OS APIs (e.g. `os.path.expanduser`, `shutil.which`).
- **Unix**: readline used when importable; external `ls`/`cat`/etc. from PATH.

---

## 8. Extension points

- **Callbacks**: Executor has settable callbacks for exit, history, source, and shell helper; Shell sets these in main or run.
- **Builtins**: New builtins: add to **builtins** (BUILTIN_HELP, handler in run_builtin_command or executor.run_command), and to BUILTIN_NAMES in executor if they should be recognized as commands.
- **Redirects**: New redirect op: add token handling in **parser.parse_redirects** and branch in **executor._apply_redirects**.

---

*Last updated with the codebase as of the initial design doc. When changing architecture or behavior, update this file and keep docs/API.md in sync with public functions.*
