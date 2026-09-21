"""Windows-safe console output (cp1251 cmd cannot print arrows)."""

from __future__ import annotations

import os
import sys


def configure_stdio() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    utf8_console = False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
            utf8_console = True
        except Exception:
            utf8_console = False
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is None:
            continue
        try:
            if utf8_console:
                reconf(encoding="utf-8", errors="replace")
            else:
                reconf(errors="replace")
        except Exception:
            pass


def ascii_safe(msg: str) -> str:
    return (
        msg.replace("\u2192", "->")
        .replace("\u2190", "<-")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u00ab", "\"")
        .replace("\u00bb", "\"")
        .replace("\u2026", "...")
    )


def say(msg: str) -> None:
    text = ascii_safe(msg)
    try:
        print(text, flush=True)
        return
    except UnicodeEncodeError:
        pass
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    data = (text + "\n").encode(enc, errors="replace")
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(data)
        buf.flush()
        return
    sys.stdout.write(data.decode(enc, errors="replace"))
    sys.stdout.flush()


def ask(prompt: str) -> str:
    say(prompt)
    try:
        return input()
    except EOFError:
        return ""
    except UnicodeEncodeError:
        say("(encoding: type Enter)")
        try:
            return sys.stdin.buffer.readline().decode("utf-8", errors="replace").rstrip("\n")
        except Exception:
            return ""
