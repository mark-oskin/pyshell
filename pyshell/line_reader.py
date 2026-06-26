"""Interactive line reading for the pyshell REPL.

Uses `prompt_toolkit` on TTYs (GNU/readline-style editing on all platforms).
Falls back to plain ``readline()`` on pipes. A minimal key-loop remains for
unit tests via ``key_source=IterableKeySource(...)``.
"""

from __future__ import annotations

import os
import sys
from typing import Callable, Iterator, Protocol

CompleteFn = Callable[[str, int], list[str]]

# Shell metacharacters that delimit completion words (``|`` must not stick to tokens).
_WORD_BREAKS = frozenset("|&;()<>")


def word_at_cursor(line: str, cursor: int) -> tuple[str, int]:
    """Return ``(word, start_index)`` for the token ending at ``cursor``."""
    cursor = max(0, min(cursor, len(line)))
    start = cursor
    while start > 0 and not line[start - 1].isspace() and line[start - 1] not in _WORD_BREAKS:
        start -= 1
    return line[start:cursor], start


def apply_completion(
    line: str, pos: int, replacement: str, *, append_space: bool = True
) -> tuple[str, int]:
    """Replace the word at ``pos`` with ``replacement``; return new line and cursor."""
    word, start = word_at_cursor(line, pos)
    if append_space and not replacement.endswith(os.sep):
        replacement = replacement + " "
    new_line = line[:start] + replacement + line[pos:]
    return new_line, start + len(replacement)


def _build_completer(complete: CompleteFn):
    from prompt_toolkit.completion import Completer, Completion

    class _ShellCompleter(Completer):
        def get_completions(self, document, complete_event):
            line = document.text
            pos = document.cursor_position
            word, start = word_at_cursor(line, pos)
            replace_len = pos - start
            for item in complete(line, pos):
                yield Completion(item, start_position=-replace_len)

    return _ShellCompleter()


def _history_from_list(entries: list[str]):
    from prompt_toolkit.history import InMemoryHistory

    hist = InMemoryHistory()
    for entry in entries:
        hist.append_string(entry)
    return hist


def read_editable_line(
    prompt: str,
    *,
    history: list[str],
    complete: CompleteFn,
    key_source: KeySource | None = None,
) -> str | None:
    """Read one edited line from a TTY, or a plain line from a pipe."""
    if key_source is not None:
        return _test_edit_loop(prompt, history=history, complete=complete, key_source=key_source)

    if not (hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
        sys.stdout.write(prompt)
        sys.stdout.flush()
        raw = sys.stdin.readline()
        if raw == "":
            return None
        return raw.rstrip("\r\n")

    from prompt_toolkit import PromptSession
    from prompt_toolkit.formatted_text import ANSI

    session = PromptSession(
        history=_history_from_list(history),
        completer=_build_completer(complete),
        enable_history_search=True,
        multiline=False,
    )

    try:
        # prompt_toolkit accepts ANSI in the prompt string (executor may emit colors).
        return session.prompt(ANSI(prompt), handle_sigint=True)
    except EOFError:
        return None


# ---------------------------------------------------------------------------
# Minimal edit loop used only by unit tests (IterableKeySource).
# ---------------------------------------------------------------------------


class KeySource(Protocol):
    def read_key(self) -> str | None:
        """Return the next key/event, or None at EOF."""


class IterableKeySource:
    """Test helper: feed normalized keys from an iterable."""

    def __init__(self, keys: Iterator[str] | list[str]) -> None:
        self._iter = iter(keys)

    def read_key(self) -> str | None:
        try:
            return next(self._iter)
        except StopIteration:
            return None


def _test_edit_loop(
    prompt: str,
    *,
    history: list[str],
    complete: CompleteFn,
    key_source: KeySource,
) -> str | None:
    """Tiny line editor for tests — not used in the interactive REPL."""
    line = ""
    pos = 0
    sys.stdout.write(prompt)
    sys.stdout.flush()
    while True:
        key = key_source.read_key()
        if key is None:
            return None
        if key in ("\r", "\n", "ENTER"):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return line
        if key == "CTRL_C":
            raise KeyboardInterrupt
        if key in ("CTRL_D", "CTRL_Z", "EOF"):
            raise EOFError
        if key in ("BACKSPACE", "DEL") and pos > 0:
            line = line[: pos - 1] + line[pos:]
            pos -= 1
            continue
        if key == "TAB":
            completions = complete(line, pos)
            if len(completions) == 1:
                line, pos = apply_completion(line, pos, completions[0])
            continue
        if len(key) == 1 and key >= " ":
            line = line[:pos] + key + line[pos:]
            pos += 1


# Backwards-compatible aliases used in tests/docs.
def redraw_line(prompt: str, line: str, pos: int, *, display_rows: int = 1) -> int:
    sys.stdout.write("\r" + " " * (len(prompt) + len(line) + 4) + "\r" + prompt + line)
    sys.stdout.flush()
    return 1


def render_multiline(prompt: str, line: str) -> str:
    indent = " " * len(prompt)
    out = [prompt]
    for ch in line:
        if ch == "\n":
            out.append("\n" + indent)
        else:
            out.append(ch)
    return "".join(out)


def rendered_cursor_index(prompt: str, line: str, pos: int) -> int:
    return len(render_multiline(prompt, line[:pos]))


def display_row_count(prompt: str, line: str) -> int:
    return line.count("\n") + 1
