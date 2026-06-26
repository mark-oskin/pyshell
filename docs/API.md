# pyshell API index

Quick index of modules and functions for navigation and tooling. Use “Search in workspace” for symbol names. Docstrings in code are the source of truth; this file is a map.

---

## pyshell (package)

- **__version__**: str — Package version.
- **main()** → int — CLI entry; run REPL, script, or `-c` command. See `shell.main`.
- **Shell** — REPL and orchestration. See `shell.Shell`.

---

## pyshell.shell

### Functions

| Function | Description |
|----------|-------------|
| **main()** → int | Parse argv; run interactive REPL, script, or `-c` command. Returns exit code. |
| **_print_usage()** → None | Print usage and options to stdout. |
| **run_script(path)** → int | Execute a pyshell script file. Returns exit code. |

### Class: ShellHelper

Exposed as `shell` in the Python namespace. **Script API** for Python code and pyshell scripts (see also `help('shell')` in the REPL).

| Method | Description |
|--------|-------------|
| **run(cmd, background=False)** → int | Run one shell command line; return exit code. background=True runs in background (adds to job list). |
| **capture(cmd)** → tuple[str, int] | Run command, return (stdout string, exit code). |
| **cd(path)** | Change directory; no args = home. |
| **pwd()** → str | Current working directory. |
| **pushd(path)** | Push cwd onto stack, cd to path; no path = swap. |
| **popd()** | Pop directory from stack and cd to it. |
| **dirs()** → str | Directory stack (cwd + pushd) as string. |
| **jobs()** → list[dict] | List of jobs: id, cmd, status ('running'\|'stopped'\|'done'), pid. |
| **fg(spec=None)** → int | Bring job to foreground; spec None or '%n'. Blocks until job finishes. |
| **bg(spec=None)** → int | Resume stopped job in background; spec None or '%n'. |
| **kill(\*args)** → int | Send signal to process/job. E.g. kill('%1'), kill('-9', '%1'). |
| **exit_code()** → int | Exit code of last command or pipeline. |
| **prompt(template=None)** → str | Get current prompt, or set prompt if template given (then return ''). |

### Class: Shell

| Method | Description |
|--------|-------------|
| **run(run_rc)** → int | Run REPL loop. run_rc=False skips .pyshellrc. Returns exit code. |
| **_run_file_in_current_shell(path)** | Run script in current namespace (source / .pyshellrc). |
| **_run_startup_config()** | Run .pyshellrc from cwd or home if present. |
| **_print_banner()** | Print startup banner. |
| **_add_history(line)** | Append line to in-memory history. |
| **_load_history()** | Load history from ~/.pyshell_history. |
| **_save_history()** | Write history to ~/.pyshell_history (last 2000 entries). |
| **_get_completions(line, cursor)** → list[str] | Tab completion list (commands, paths, $vars) for word at cursor. |
| **_has_unclosed_delimiters(text)** → bool | True if more input needed (unclosed quotes/brackets). |
| **_find_matching_paren(s, open_idx)** → int | Index of matching ')'; -1 if not found. |
| **_is_subshell(line)** → bool | True if line is ( ... ) subshell form. |
| **_extract_subshell_content(line)** → str | Content between ( and ) for subshell. |
| **_eval(line)** | Evaluate one logical line (conditionals, Python, command, pipeline). |
| **_eval_conditional(segments, redirects, background)** | Run &&/|| chain. |
| **_eval_one(cmd_line, redirects, background)** | Dispatch to Python or run_command/run_pipeline. |
| **_read_editable(prompt)** → str \| None | Read one line with the prompt_toolkit (TTY). |
| **_read_line()** → str \| None | Read one logical line: `\` continuation, unclosed delimiters, then **python_block_continuation_needed**; multiline history bypasses re-prompting. |
| **get_history()** → list[str] | Return history list (for history builtin). |
| **request_exit(code)** | Set _running=False and raise SystemExit. |

#### Multiline input (`_read_line`)

1. **Trailing `\`** — append next physical line (`...` prompt).
2. **Unclosed delimiters** — quotes/brackets; append until balanced.
3. **python_block_continuation_needed** — compound Python header missing body (e.g. `for i in range(3):`).

Embedded `\n` from recalled history skips steps 1–3. Pipeline lines with unquoted `|` need `\` on each continued line because step 3 does not apply to shell prefixes like `cat f |`.

---

## pyshell.line_reader

| Function | Description |
|----------|-------------|
| **read_editable_line(prompt, \*, history, complete, key_source=None)** → str \| None | TTY: prompt_toolkit; pipe: ``readline()``; tests: ``key_source``. |
| **word_at_cursor(line, cursor)** → tuple[str, int] | Word ending at cursor and its start index. |
| **apply_completion(line, pos, replacement, \*, append_space=True)** → tuple[str, int] | Replace word at cursor with completion. |
| **IterableKeySource** | Test helper: feed normalized key events from an iterable. |

---

## pyshell.parser

| Function | Description |
|----------|-------------|
| **parse_line(line)** → tuple | Classify line: ("python", source) or ("command", argv) or ("pipeline", list of argv). |
| **is_complete_python(source)** → bool | True if source is syntactically complete Python (module mode). |
| **python_block_continuation_needed(source)** → bool | True when source is a compound header (e.g. `for`/`while`/`if`) still missing its body. |
| **_is_single_identifier(line)** → bool | True if line is exactly one identifier. |
| **_is_python(line)** → bool | True if line parses as valid Python. |
| **has_unquoted_redirect_or_background(line)** → bool | True if redirect tokens or trailing & outside quotes. |
| **_pipe_not_inside_quotes(line)** → bool | True if unquoted \| present. |
| **_split_pipeline(line)** → list[str] | Split by \| respecting quotes; segment strings. |
| **has_conditional(line)** → bool | True if unquoted && or \|\|. |
| **split_conditional(line)** → list[tuple] | Split by &&/\|\|; [(segment, connector), ...]. |
| **parse_redirects(line)** → tuple | (argv, redirects, background). redirects: (op, path). |
| **_split_command(line)** → list[str] | Tokenize command line respecting quotes. |

---

## pyshell.executor

### Class: Executor

| Method | Description |
|--------|-------------|
| **set_shell_helper(helper)** | Set object exposed as `shell` in namespace. |
| **set_exit_callback(callback)** | Callback for exit(code). |
| **set_history_callback(callback)** | Callback returning history list. |
| **set_prompt(s)** | Set prompt template; None = default. Placeholders: {cwd}, {base}, etc. |
| **set_source_callback(callback)** | Callback(path) to run script in current shell. |
| **get_aliases()** → dict | Copy of aliases. |
| **set_alias(name, value)** | Define alias. |
| **unalias(name)** | Remove alias. |
| **_get_namespace()** → dict | Namespace for Python (env, builtins, last_exit_code, shell). |
| **_set_exit_code(code)** | Set _last_exit_code and namespace["last_exit_code"]. |
| **get_prompt()** → str | Current prompt string (placeholders expanded). |
| **get_jobs()** → list[dict] | Snapshot of job list: id, cmd, status ('running'\|'stopped'\|'done'), pid. |
| **run_python(source, original_line)** | Execute Python source; return value for expressions. |
| **run_command(argv, redirects, background)** | Run one command (builtin or external). |
| **run_pipeline(segments, redirects, background, segment_sources=None)** | Run pipeline; redirects on last stage. With **segment_sources**, stages whose text is valid Python run in the REPL namespace (prior stdout → **sys.stdin**). |
| **_run_python_pipeline_stage(source, stdin_text)** → str | Execute one Python pipeline stage; return captured stdout for the next stage. |

#### Jobs and job control

- **Starting jobs**  
  - **Foreground**: `run_command(argv, redirects, background=False)` (default). Runs the command and waits; on Unix with a TTY, Ctrl+Z suspends it and adds it to the job list.  
  - **Background**: `run_command(argv, redirects, background=True)` or `run_pipeline(..., background=True)`. Starts the command (or last stage) in the background and adds it to the job list; returns immediately.

- **Listing jobs**  
  - **Shell**: `jobs` builtin prints id, pid, status (running/stopped/done), and command.  
  - **API**: `get_jobs()` returns a list of dicts with `id`, `cmd`, `status`, `pid` for programmatic use.

- **Job control (shell builtins)**  
  - **fg [%jobid]** — Bring a job to the foreground; wait for it. Optional `%n` selects job by id; no arg = most recent. On Unix, sends SIGCONT if the job was stopped and restores the terminal.  
  - **bg [%jobid]** — Resume a stopped job in the background (sends SIGCONT). Optional `%n` selects job; no arg = most recent.  
  - **kill [-signal] pid | %jobid [...]** — Send a signal (default SIGTERM) to process(es) or job(s). E.g. `kill -9 %1`, `kill %1`.

- **Platform**  
  - **Unix (TTY)**: Full job control (suspend with Ctrl+Z, fg/bg with terminal handoff).  
  - **Windows**: Background jobs and `fg` (wait) work; no suspend (Ctrl+Z) or process-group signals.

### Module-level functions

| Function | Description |
|----------|-------------|
| **_safe_stdin()** | stdin for subprocess; DEVNULL if no fileno. |
| **_has_fileno(stream)** → bool | True if stream has fileno(). |
| **_apply_redirects(redirects)** → tuple | (stdout_f, stderr_f, stdin_f, stderr_to_stdout). |
| **_run_builtin_jobs(jobs)** | Print job list (id, pid, status, cmd). |
| **_run_builtin_fg(jobs, set_exit_code, job_spec)** | Bring job to foreground; job_spec None or '%n'. |
| **_run_builtin_bg(jobs, job_spec)** | Resume stopped job in background; returns 'ok'\|'no_job'\|'not_stopped'. |
| **_run_builtin_kill(args, jobs, set_exit_code)** | kill [-signal] pid \| %jobid [...]. |
| **_is_expression_statement(tree)** → bool | True if AST is single expression. |
| **_is_bare_name(tree)** → bool | True if AST is single Name. |

Command PATH resolution lives in **pyshell.command_resolve** (see below).

---

## pyshell.subprocess_env

| Function | Description |
|----------|-------------|
| **subprocess_env()** → dict[str, str] | Copy of ``os.environ`` for child processes; drops ``VIRTUAL_ENV`` when it does not match ``<cwd>/.venv``. |

---

## pyshell.command_resolve

| Function | Description |
|----------|-------------|
| **path_lookup_names(name)** → list[str] | Ordered PATH names to try (``program`` → ``program``, ``program.py``; ``program.`` → ``program.py``). |
| **resolve_command_argv(argv, \*, path_env=None)** → list \| None | Resolve ``argv[0]``; non-executable ``.py`` on PATH runs via ``sys.executable``. |
| **lookup_command(name, \*, path_env=None)** → str \| None | Path for ``which`` / ``type`` (script path when run via Python). |

---

## pyshell.builtins

### Constants

- **BUILTIN_HELP**: dict[str, str] — One-line help per builtin.
- **EXTENDED_HELP**: dict[str, str] — Long help for prompt, quoting, windows.

### Functions

| Function | Description |
|----------|-------------|
| **run_mkdir(argv)** → bool | Create dirs; -p for parents. Return True if all ok. |
| **run_cat(argv)** → str | Print file contents (Windows builtin). |
| **run_echo(argv)** → str | Print args; -n = no newline (Windows builtin). |
| **run_ls_dir(argv)** → str | List directory like ls (Windows builtin). |
| **make_builtins(exit_callback, get_history, aliases, set_prompt)** → dict | Build namespace of Python callables (cd, pwd, run, help, etc.). |
| **run_builtin_command(name, args)** → str \| int \| None | Run builtin by name; None if not a builtin. |

---

## pyshell.expansion

| Function | Description |
|----------|-------------|
| **expand_vars_in_string(s, env)** → str | Replace $VAR and ${VAR} from env. |
| **expand_tilde(s)** → str | Expand ~ and ~user to home path. |
| **expand_glob_argv(argv)** → list[str] | Expand tokens containing *, ?, ** to paths. |
| **expand_command_argv(argv, env)** → list[str] | Apply vars, tilde, then glob to argv. |
| **expand_redirect_path(path, env)** → str \| None | Expand $VAR and ~ in redirect path. |

---

*When adding or changing public functions, update this index and the corresponding docstrings in code.*
