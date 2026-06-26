"""Cross-platform interactive line editing without GNU readline/libedit.

pyshell uses this module for all TTY input so behavior is consistent on macOS
(libedit), Linux, and Windows. Non-TTY stdin falls back to ``readline()``.
"""

from __future__ import annotations

import os
import shutil
import sys
import termios
import tty
from typing import Callable, Iterator, Protocol

if os.name == "nt":
    import msvcrt
else:
    msvcrt = None  # type: ignore


CompleteFn = Callable[[str, int], list[str]]


def _tty_nl() -> str:
    """Newline for terminal output (LF-only leaves cursor mid-row in raw TTY mode)."""
    return "\r\n"


def _clear_line() -> str:
    """Clear the current terminal row and move to column 0."""
    return "\033[2K\r"


# Shell metacharacters that delimit completion words (``|`` must not stick to tokens).
_WORD_BREAKS = frozenset("|&;()<>")


def _history_edit_line(entry: str) -> str:
    """Flatten a multi-line history entry for single-row editing."""
    return " ".join(entry.split())


def _display_line(line: str) -> str:
    """Render buffer as one terminal row (no embedded newlines)."""
    return line.replace("\n", " ").replace("\r", "")


def _terminal_cols() -> int:
    try:
        return shutil.get_terminal_size(fallback=(80, 24)).columns
    except OSError:
        return 80


def _display_rows(prompt: str, line: str) -> int:
    cols = _terminal_cols()
    length = len(prompt) + len(_display_line(line))
    return max(1, (length + cols - 1) // cols)


def _clear_display_rows(rows: int) -> None:
    """Clear ``rows`` terminal rows ending at the current cursor row."""
    if rows < 1:
        return
    sys.stdout.write(_clear_line())
    for _ in range(rows - 1):
        sys.stdout.write("\033[1A" + _clear_line())


def _cursor_to_display_pos(display_pos: int, content_len: int, cols: int) -> None:
    """Move cursor from end-of-content to ``display_pos`` (0-based)."""
    if display_pos >= content_len:
        return
    end_row = (content_len - 1) // cols
    end_col = (content_len - 1) % cols
    target_row = display_pos // cols
    target_col = display_pos % cols
    row_up = end_row - target_row
    if row_up:
        sys.stdout.write(f"\033[{row_up}A")
        sys.stdout.write(f"\033[{target_col + 1}G")
    else:
        sys.stdout.write("\b" * (end_col - target_col))


class KeySource(Protocol):
    def read_key(self) -> str | None:
        """Return the next key/event, or None at EOF."""


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


def redraw_line(prompt: str, line: str, pos: int, *, display_rows: int = 1) -> int:
    """Rewrite prompt + line on the terminal and place the cursor.

    Returns:
        Number of terminal rows used by the redrawn content.
    """
    display = _display_line(line)
    content = prompt + display
    cols = _terminal_cols()

    _clear_display_rows(display_rows)
    sys.stdout.write(content)

    display_pos = len(prompt) + len(_display_line(line[:pos]))
    _cursor_to_display_pos(display_pos, len(content), cols)
    sys.stdout.flush()
    return _display_rows(prompt, line)


def _edit_loop(
    prompt: str,
    *,
    history: list[str],
    complete: CompleteFn,
    key_source: KeySource,
) -> str | None:
    line = ""
    pos = 0
    history_index = len(history)
    saved_edit = ""
    display_rows = 1

    while True:
        key = key_source.read_key()
        if key is None:
            return None
        if key in ("\r", "\n", "ENTER"):
            sys.stdout.write(_tty_nl())
            sys.stdout.flush()
            return line
        if key == "CTRL_C":
            raise KeyboardInterrupt
        if key in ("CTRL_D", "CTRL_Z", "EOF"):
            raise EOFError
        if key in ("HOME", "CTRL_A"):
            if pos > 0:
                sys.stdout.write("\b" * pos)
                sys.stdout.flush()
                pos = 0
            continue
        if key in ("END", "CTRL_E"):
            if pos < len(line):
                sys.stdout.write(line[pos:])
                sys.stdout.flush()
                pos = len(line)
            continue
        if key == "LEFT":
            if pos > 0:
                pos -= 1
                sys.stdout.write("\b")
                sys.stdout.flush()
            continue
        if key == "RIGHT":
            if pos < len(line):
                sys.stdout.write(line[pos])
                pos += 1
                sys.stdout.flush()
            continue
        if key == "UP":
            if history:
                if history_index >= len(history):
                    saved_edit = line
                history_index = max(0, history_index - 1)
                line = _history_edit_line(history[history_index])
                pos = len(line)
                display_rows = redraw_line(prompt, line, pos, display_rows=display_rows)
            continue
        if key == "DOWN":
            if history:
                history_index = min(len(history), history_index + 1)
                if history_index >= len(history):
                    line = saved_edit
                else:
                    line = _history_edit_line(history[history_index])
                pos = len(line)
                display_rows = redraw_line(prompt, line, pos, display_rows=display_rows)
            continue
        if key in ("BACKSPACE", "DEL"):
            if pos > 0:
                line = line[: pos - 1] + line[pos:]
                pos -= 1
                sys.stdout.write("\b")
                sys.stdout.write(line[pos:] + " ")
                sys.stdout.write("\b" * (len(line) - pos + 1))
                sys.stdout.flush()
            continue
        if key == "TAB":
            word, _start = word_at_cursor(line, pos)
            completions = complete(line, pos)
            if not completions:
                continue
            if len(completions) == 1:
                line, pos = apply_completion(line, pos, completions[0])
            else:
                prefix = os.path.commonprefix(completions)
                if prefix and prefix != word:
                    line, pos = apply_completion(line, pos, prefix, append_space=False)
                else:
                    sys.stdout.write(_tty_nl())
                    for item in sorted(completions)[:20]:
                        sys.stdout.write(item + "  ")
                    sys.stdout.write(_tty_nl())
                    sys.stdout.write(_tty_nl())
                    redraw_line(prompt, line, pos, display_rows=display_rows)
                    continue
            display_rows = redraw_line(prompt, line, pos, display_rows=display_rows)
            continue
        if len(key) == 1 and key >= " ":
            history_index = len(history)
            if pos < len(line):
                line = line[:pos] + key + line[pos:]
                pos += 1
                sys.stdout.write(key)
                sys.stdout.write(line[pos:])
                sys.stdout.write("\b" * (len(line) - pos))
            else:
                line += key
                pos += 1
                sys.stdout.write(key)
            sys.stdout.flush()


def read_editable_line(
    prompt: str,
    *,
    history: list[str],
    complete: CompleteFn,
    key_source: KeySource | None = None,
) -> str | None:
    """Read one edited line from a TTY, or a plain line from a pipe."""
    if key_source is not None:
        sys.stdout.write(_clear_line() + prompt)
        sys.stdout.flush()
        return _edit_loop(prompt, history=history, complete=complete, key_source=key_source)

    if not (hasattr(sys.stdin, "isatty") and sys.stdin.isatty()):
        sys.stdout.write(prompt)
        sys.stdout.flush()
        raw = sys.stdin.readline()
        if raw == "":
            return None
        return raw.rstrip("\r\n")

    sys.stdout.write(_clear_line() + prompt)
    sys.stdout.flush()

    if msvcrt is not None:
        return _edit_loop(prompt, history=history, complete=complete, key_source=_MsvcrtKeySource())

    unix = _UnixKeySource()
    try:
        return _edit_loop(prompt, history=history, complete=complete, key_source=unix)
    finally:
        unix.close()


class _MsvcrtKeySource:
    def read_key(self) -> str | None:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            scan = msvcrt.getwch()
            if ch == "\xe0":
                if scan == "H":
                    return "UP"
                if scan == "P":
                    return "DOWN"
                if scan == "K":
                    return "LEFT"
                if scan == "M":
                    return "RIGHT"
                if scan == "G":
                    return "HOME"
                if scan == "O":
                    return "END"
            return ""
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x1a":
            return "CTRL_Z"
        if ch == "\x04":
            return "CTRL_D"
        if ch == "\x01":
            return "CTRL_A"
        if ch == "\x05":
            return "CTRL_E"
        if ch in ("\b", "\x7f"):
            return "BACKSPACE"
        if ch == "\t":
            return "TAB"
        return ch


class _UnixKeySource:
    """Raw-mode stdin reader; call ``close()`` to restore the TTY."""

    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(self._fd)
        tty.setraw(self._fd)

    def close(self) -> None:
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def read_key(self) -> str | None:
        try:
            ch = sys.stdin.read(1)
        except EOFError:
            return None
        if ch == "":
            return None
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x04":
            return "CTRL_D"
        if ch == "\x1a":
            return "CTRL_Z"
        if ch == "\x01":
            return "CTRL_A"
        if ch == "\x05":
            return "CTRL_E"
        if ch in ("\b", "\x7f"):
            return "BACKSPACE"
        if ch == "\t":
            return "TAB"
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\x1b":
            return self._read_escape() or ch
        return ch

    def _read_escape(self) -> str:
        ch2 = sys.stdin.read(1)
        if ch2 == "":
            return ""
        if ch2 == "O":
            ch3 = sys.stdin.read(1)
            if ch3 == "H":
                return "HOME"
            if ch3 == "F":
                return "END"
            return ""
        if ch2 != "[":
            return ""
        ch3 = sys.stdin.read(1)
        if ch3 == "A":
            return "UP"
        if ch3 == "B":
            return "DOWN"
        if ch3 == "C":
            return "RIGHT"
        if ch3 == "D":
            return "LEFT"
        if ch3 == "H":
            return "HOME"
        if ch3 == "F":
            return "END"
        if ch3.isdigit():
            while True:
                n = sys.stdin.read(1)
                if n in ("", "~"):
                    break
            if ch3 == "3":
                return "DEL"
        return ""


class IterableKeySource:
    """Test helper: feed normalized keys from an iterable."""

    def __init__(self, keys: Iterator[str] | list[str]) -> None:
        self._iter = iter(keys)

    def read_key(self) -> str | None:
        try:
            return next(self._iter)
        except StopIteration:
            return None
