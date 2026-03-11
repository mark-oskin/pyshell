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

Exposed as `shell` in the Python namespace.

| Method | Description |
|--------|-------------|
| **run(cmd)** → int | Run one shell command line; return exit code. |
| **capture(cmd)** → tuple[str, int] | Run command, return (stdout string, exit code). |
| **cd(path)** | Change directory; no args = home. |
| **pwd()** → str | Current working directory. |
| **pushd(path)** | Push cwd onto stack, cd to path; no path = swap. |
| **popd()** | Pop directory from stack and cd to it. |
| **dirs()** → str | Directory stack (cwd + pushd) as string. |

### Class: Shell

| Method | Description |
|--------|-------------|
| **run(run_rc)** → int | Run REPL loop. run_rc=False skips .pyshellrc. Returns exit code. |
| **_run_file_in_current_shell(path)** | Run script in current namespace (source / .pyshellrc). |
| **_run_startup_config()** | Run .pyshellrc from cwd or home if present. |
| **_print_banner()** | Print startup banner. |
| **_add_history(line)** | Append line to history and readline (if available). |
| **_load_history()** | Load history from ~/.pyshell_history. |
| **_save_history()** | Write history to ~/.pyshell_history (last 2000 entries). |
| **_setup_completion()** | Register readline completer. |
| **_completer(text, state)** | Readline completer callback. |
| **_get_completions(text)** → list[str] | Tab completion list (commands, paths, $vars). |
| **_has_unclosed_delimiters(text)** → bool | True if more input needed (unclosed quotes/brackets). |
| **_find_matching_paren(s, open_idx)** → int | Index of matching ')'; -1 if not found. |
| **_is_subshell(line)** → bool | True if line is ( ... ) subshell form. |
| **_extract_subshell_content(line)** → str | Content between ( and ) for subshell. |
| **_eval(line)** | Evaluate one logical line (conditionals, Python, command, pipeline). |
| **_eval_conditional(segments, redirects, background)** | Run &&/|| chain. |
| **_eval_one(cmd_line, redirects, background)** | Dispatch to Python or run_command/run_pipeline. |
| **_read_line_fallback(prompt)** → str \| None | Windows key-by-key line input with history and cursor. |
| **_read_line()** → str \| None | Read one line with continuation. |
| **get_history()** → list[str] | Return history list (for history builtin). |
| **request_exit(code)** | Set _running=False and raise SystemExit. |

---

## pyshell.parser

| Function | Description |
|----------|-------------|
| **parse_line(line)** → tuple | Classify line: ("python", source) or ("command", argv) or ("pipeline", list of argv). |
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
| **run_python(source, original_line)** | Execute Python source; return value for expressions. |
| **run_command(argv, redirects, background)** | Run one command (builtin or external). |
| **run_pipeline(segments, redirects, background)** | Run pipeline; redirects on last stage. |

### Module-level functions

| Function | Description |
|----------|-------------|
| **_safe_stdin()** | stdin for subprocess; DEVNULL if no fileno. |
| **_has_fileno(stream)** → bool | True if stream has fileno(). |
| **_apply_redirects(redirects)** → tuple | (stdout_f, stderr_f, stdin_f, stderr_to_stdout). |
| **_run_builtin_jobs(jobs)** | Print job list. |
| **_run_builtin_fg(jobs, set_exit_code)** | Wait for last job, set exit code. |
| **_run_builtin_bg(jobs)** | No-op for already-running jobs. |
| **_is_expression_statement(tree)** → bool | True if AST is single expression. |
| **_is_bare_name(tree)** → bool | True if AST is single Name. |
| **_resolve_command_argv(argv)** → list \| None | Resolve command via PATH; None if not found. |

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
