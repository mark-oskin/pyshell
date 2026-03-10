# pyshell – work items (missing / limited features)

Numbered for reference. Priorities are suggestions.

---

## Input / redirects

1. **Heredoc** – `<<EOF` / `<<'EOF'` for multi-line stdin.
2. **Command substitution** – `$(cmd)` or `` `cmd` `` to substitute command output into the command line.

---

## Line editing (Windows fallback)

3. **History search** – e.g. Ctrl+R in Windows fallback (on Unix depends on readline).

---

## Shell conveniences

4. **`read` builtin** – Read a line from stdin into a variable (for scripts).
5. **`export` builtin** – Export a variable into the environment for child processes from shell syntax.
6. **`exec` builtin** – Replace shell with command.

---

## Advanced expansion

7. **Brace expansion** – `{a,b,c}` or `{1..10}`.

---

## Job / process control

8. **Suspend (e.g. Ctrl+Z)** – Suspend foreground process and put in job list.
9. **Job control in pipelines** – Clarify or implement per-stage vs single job for pipelines.

---

## Scripting / robustness

10. **`set -e` style** – Option to exit script on first command failure.
11. **`trap`** – Shell-level signal handlers (e.g. cleanup on INT/TERM).
12. **`ulimit`** – Interface to resource limits.

---

## Documentation / polish

13. **History file format** – Document format (escaping, one entry per line, max entries) in README or help.

---

## Suggested priority order

| #  | Item | Priority |
|----|------|----------|
| 1  | Heredoc | Medium |
| 2  | Command substitution | Medium |
| 4  | `read` builtin | Medium |
| 5  | `export` builtin | Medium |
| 3, 6–13 | Remainder | Lower |
