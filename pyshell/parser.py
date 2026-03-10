"""Parse user input: distinguish Python-like code from shell commands."""

import ast


def parse_line(line: str) -> tuple[str, str | list | list[list[str]]]:
    """
    Classify a line as Python-like code, a command, or a pipeline.

    Returns:
        ("python", source) if the line is valid Python.
        ("command", [cmd, arg1, ...]) for a single command.
        ("pipeline", [[cmd1, ...], [cmd2, ...], ...]) for cmd1 | cmd2.
    """
    line_stripped = line.strip()
    if not line_stripped:
        return ("python", "")

    def as_command() -> tuple[str, list[str] | list[list[str]]]:
        """Return (kind, payload); if line has |, return pipeline."""
        if "|" in line_stripped and _pipe_not_inside_quotes(line):
            segments = _split_pipeline(line)
            if len(segments) >= 2:
                return ("pipeline", [_split_command(seg) for seg in segments])
        return ("command", _split_command(line))

    # Unquoted | means pipeline (e.g. "ls|wc"); prefer over Python so we don't run "ls|wc" as Python.
    if "|" in line_stripped and _pipe_not_inside_quotes(line):
        segments = _split_pipeline(line)
        if len(segments) >= 2:
            return ("pipeline", [_split_command(seg) for seg in segments])

    # Single identifier (e.g. ls, pwd) → command (or pipeline)
    if _is_single_identifier(line_stripped):
        return as_command()

    # Multiple tokens starting with an identifier (e.g. ls -la) → command,
    # but not if it looks like Python (assignment or call).
    if "=" not in line_stripped and "(" not in line_stripped:
        parts = line_stripped.split()
        if len(parts) >= 2 and parts[0].isidentifier():
            return as_command()

    if _is_python(line_stripped):
        return ("python", line)
    return as_command()


def _is_single_identifier(line: str) -> bool:
    """True if the line is exactly one identifier (e.g. ls, pwd). Run as command."""
    s = line.strip()
    if not s:
        return False
    parts = s.split()
    if len(parts) != 1:
        return False
    return parts[0].isidentifier()


def _is_python(line: str) -> bool:
    """Return True if the line is valid Python (expression or statement)."""
    try:
        ast.parse(line)
        return True
    except SyntaxError:
        pass
    # Also try as expression only (e.g. "2 + 3")
    try:
        ast.parse(line, mode="eval")
        return True
    except SyntaxError:
        pass
    return False


def has_unquoted_redirect_or_background(line: str) -> bool:
    """True if the line contains redirect tokens or trailing & outside quotes."""
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            i += 1
            continue
        if c == "&" and i == n - 1:
            return True
        if c == ">" and i + 1 < n and line[i + 1] in (">", "=", "&"):
            if line[i : i + 3] == ">&1" or line[i : i + 2] in (">>", ">="):
                return True
        if c == ">" and (i + 1 >= n or line[i + 1] in (" ", "\t", ">", "&")):
            return True
        if c == "<" and (i + 1 >= n or line[i + 1] in (" ", "\t")):
            return True
        if c == "<" and i + 2 < n and line[i : i + 3] == "<<<":
            return True
        if c == "2" and i + 2 <= n and line[i + 1] == ">" and (line[i + 2] in (" ", "\t", "&") or i + 2 == n):
            return True
        i += 1
    return False


def _pipe_not_inside_quotes(line: str) -> bool:
    """True if there is a | that is not inside quotes (so we can split pipeline)."""
    quote: str | None = None
    for i, c in enumerate(line):
        if quote:
            if c == quote:
                quote = None
            continue
        if c in ("'", '"'):
            quote = c
            continue
        if c == "|":
            return True
    return False


def _split_pipeline(line: str) -> list[str]:
    """Split line by |, respecting quotes. Returns list of segment strings."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == "\\" and i + 1 < n:
                current.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
                i += 1
                continue
            current.append(c)
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            current.append(c)
            i += 1
            continue
        if c == "|":
            segments.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(c)
        i += 1
    if current:
        segments.append("".join(current).strip())
    return segments


def has_conditional(line: str) -> bool:
    """True if line contains unquoted && or ||."""
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            i += 1
            continue
        if i + 1 < n and line[i : i + 2] == "&&":
            return True
        if i + 1 < n and line[i : i + 2] == "||":
            return True
        i += 1
    return False


def split_conditional(line: str) -> list[tuple[str, str | None]]:
    """Split by && and || (respecting quotes). Returns [(segment, connector), ...], connector is '&&', '||', or None."""
    result: list[tuple[str, str | None]] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if quote:
            if c == quote:
                quote = None
            current.append(c)
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            current.append(c)
            i += 1
            continue
        if i + 1 < n and line[i : i + 2] == "&&":
            result.append(("".join(current).strip(), "&&"))
            current = []
            i += 2
            continue
        if i + 1 < n and line[i : i + 2] == "||":
            result.append(("".join(current).strip(), "||"))
            current = []
            i += 2
            continue
        current.append(c)
        i += 1
    if current:
        result.append(("".join(current).strip(), None))
    return result


def parse_redirects(line: str) -> tuple[list[str], list[tuple[str, str | None]], bool]:
    """
    Split line into argv, redirects, and background flag.
    Returns (argv, redirects, background).
    redirects: list of (op, path) with op in (">", ">>", "<", "2>", "2>>", "2>&1"); path is None for 2>&1.
    """
    tokens = _split_command(line)
    argv: list[str] = []
    redirects: list[tuple[str, str | None]] = []
    background = False
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "&" and i == len(tokens) - 1:
            background = True
            i += 1
            continue
        if t == "2>&1":
            redirects.append(("2>&1", None))
            i += 1
            continue
        if t == "2" and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt == ">&1":
                redirects.append(("2>&1", None))
                i += 2
                continue
            if nxt == ">" and i + 2 <= len(tokens):
                redirects.append(("2>", tokens[i + 2]))
                i += 3
                continue
            if nxt == ">>" and i + 2 <= len(tokens):
                redirects.append(("2>>", tokens[i + 2]))
                i += 3
                continue
        if t == "<<<" and i + 1 < len(tokens):
            redirects.append(("<<<", tokens[i + 1]))
            i += 2
            continue
        if t in (">", ">>", "<") and i + 1 < len(tokens):
            redirects.append((t, tokens[i + 1]))
            i += 2
            continue
        if t == "2>" and i + 1 < len(tokens):
            redirects.append(("2>", tokens[i + 1]))
            i += 2
            continue
        if t == "2>>" and i + 1 < len(tokens):
            redirects.append(("2>>", tokens[i + 1]))
            i += 2
            continue
        argv.append(t)
        i += 1
    return (argv, redirects, background)


def _split_command(line: str) -> list[str]:
    """Split a command line into words, respecting double and single quotes."""
    tokens: list[str] = []
    current: list[str] = []
    i = 0
    n = len(line)
    quote: str | None = None

    while i < n:
        c = line[i]
        if quote:
            if c == "\\" and i + 1 < n:
                current.append(line[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
                i += 1
                continue
            current.append(c)
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
            i += 1
            continue
        if c in (" ", "\t"):
            if current:
                tokens.append("".join(current))
                current = []
            i += 1
            continue
        current.append(c)
        i += 1

    if current:
        tokens.append("".join(current))
    return tokens
