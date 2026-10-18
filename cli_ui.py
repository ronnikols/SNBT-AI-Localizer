"""Terminal presentation layer for the snbt-tr CLI.

Rich is optional: without it (or with --no-color / NO_COLOR / TERM=dumb)
everything degrades to plain text with the same semantics.
All prompts go through builtins.input() so they stay scriptable/testable.
"""
import logging
import os
import sys
import time
from typing import Iterable, Optional, Sequence

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.progress import (Progress, SpinnerColumn, BarColumn, TextColumn,
                               MofNCompleteColumn, TimeElapsedColumn, TimeRemainingColumn)
    from rich.theme import Theme
    from rich import box
    HAS_RICH = True
except Exception:  # pragma: no cover
    HAS_RICH = False

_THEME = {
    "info": "cyan",
    "ok": "bold green",
    "warn": "bold yellow",
    "err": "bold red",
    "accent": "bold magenta",
    "key": "bold cyan",
}

LEVEL_STYLE = {
    logging.DEBUG: ("dim", "·"),
    logging.INFO: ("", "•"),
    logging.WARNING: ("warn", "!"),
    logging.ERROR: ("err", "✖"),
    logging.CRITICAL: ("err", "✖"),
}


def _no_color_env() -> bool:
    return bool(os.environ.get("NO_COLOR")) or os.environ.get("TERM") == "dumb"


def _plain(msg: str) -> str:
    if HAS_RICH:
        try:
            return Text.from_markup(msg).plain
        except Exception:
            return msg
    return msg


class UI:
    def __init__(self):
        self.color = HAS_RICH and not _no_color_env()
        self.console = Console(theme=Theme(_THEME), highlight=False, no_color=not self.color) if HAS_RICH else None

    def configure(self, color: Optional[bool] = None):
        if not HAS_RICH:
            self.color = False
            return
        self.color = not (color is False or _no_color_env())
        self.console = Console(theme=Theme(_THEME), highlight=False, no_color=not self.color)

    @property
    def rich(self) -> bool:
        return HAS_RICH and self.console is not None

    # ---- raw output -----------------------------------------------------
    def print(self, msg: str = "", style: str = ""):
        if self.rich:
            self.console.print(msg, style=style or None, markup=True, emoji=False)
        else:
            print(_plain(msg))

    def plain(self, msg: str):
        if self.rich:
            self.console.print(msg, markup=False, emoji=False, highlight=False)
        else:
            print(msg)

    def rule(self, title: str = ""):
        if self.rich:
            self.console.rule(f"[accent]{title}[/]" if title else "", style="dim")
        else:
            print(f"--- {title} ---" if title else "-" * 40)

    def info(self, msg: str):
        self._line(msg, "", "•")

    def ok(self, msg: str):
        self._line(msg, "ok", "✔")

    def warn(self, msg: str):
        self._line(msg, "warn", "!")

    def err(self, msg: str):
        self._line(msg, "err", "✖")

    def _line(self, msg: str, style: str, glyph: str):
        if self.rich:
            t = Text(f"{glyph} ", style=style or "dim")
            t.append(msg, style=style or "")
            self.console.print(t)
        else:
            print(f"{glyph} {msg}")

    def log_record(self, record: logging.LogRecord):
        style, glyph = LEVEL_STYLE.get(record.levelno, ("", "•"))
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + logging.Formatter().formatException(record.exc_info)
        self._line(msg, style, glyph)

    # ---- blocks ---------------------------------------------------------
    def banner(self, version: str, subtitle: str = ""):
        if self.rich:
            body = Text()
            body.append("SNBT AI Localizer", style="bold magenta")
            body.append(f"  v{version}", style="dim")
            if subtitle:
                body.append(f"\n{subtitle}", style="dim")
            self.console.print(Panel(body, box=box.ROUNDED, border_style="magenta", expand=False, padding=(0, 2)))
        else:
            print(f"=== SNBT AI Localizer v{version} ===")
            if subtitle:
                print(subtitle)

    def kv(self, title: str, pairs: Sequence[tuple], style: str = "cyan"):
        if self.rich:
            t = Table.grid(padding=(0, 2))
            t.add_column(style="dim", justify="right")
            t.add_column()
            for k, v in pairs:
                t.add_row(str(k), str(v))
            self.console.print(Panel(t, title=title, border_style=style, box=box.ROUNDED, expand=False, padding=(0, 1)))
        else:
            print(f"[{title}]")
            for k, v in pairs:
                print(f"  {k}: {_plain(str(v))}")

    def table(self, title: str, columns: Sequence[str], rows: Iterable[Sequence], styles: Optional[Sequence[str]] = None,
              ratios: Optional[Sequence[Optional[int]]] = None):
        rows = [list(r) for r in rows]
        if self.rich:
            t = Table(title=title or None, box=box.SIMPLE_HEAD, header_style="bold cyan",
                      title_style="accent", expand=bool(ratios))
            for i, c in enumerate(columns):
                ratio = ratios[i] if ratios and i < len(ratios) else None
                t.add_column(c, style=(styles[i] if styles and i < len(styles) else None), overflow="fold",
                             ratio=ratio, no_wrap=(ratio is None and bool(ratios)))
            for r in rows:
                t.add_row(*[str(x) for x in r])
            self.console.print(t)
        else:
            if title:
                print(title)
            widths = [max([len(str(c))] + [len(_plain(str(r[i]))) for r in rows]) for i, c in enumerate(columns)]
            print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(columns)))
            for r in rows:
                print("  ".join(_plain(str(x)).ljust(widths[i]) for i, x in enumerate(r)))

    def menu(self, title: str, items: Sequence[tuple], default_idx: int = 0, extra: Sequence[str] = ()):
        """items: (label, note). Numbered list, extra entries appended after."""
        if self.rich:
            t = Table(box=None, show_header=False, padding=(0, 1), expand=False)
            t.add_column(style="key", justify="right")
            t.add_column()
            t.add_column(style="dim")
            for i, (label, note) in enumerate(items):
                mark = "▸" if i == default_idx else " "
                t.add_row(f"{mark}{i + 1})", label, note or "")
            for j, label in enumerate(extra):
                t.add_row(f" {len(items) + j + 1})", f"[dim]{label}[/]", "")
            self.console.print(Panel(t, title=title, border_style="cyan", box=box.ROUNDED, expand=False, padding=(0, 1)))
        else:
            print(title)
            for i, (label, note) in enumerate(items):
                print(f"  {i + 1}) {_plain(label)}{(' ' + _plain(note)) if note else ''}")
            for j, label in enumerate(extra):
                print(f"  {len(items) + j + 1}) {label}")

    # ---- prompts (builtins.input only) ----------------------------------
    def _prompt_str(self, text: str, default: Optional[str] = None) -> str:
        if self.color:
            d = f" \x1b[2m[{default}]\x1b[0m" if default not in (None, "") else ""
            return f"\x1b[1;36m?\x1b[0m {text}{d}: "
        d = f" [{default}]" if default not in (None, "") else ""
        return f"? {text}{d}: "

    def ask(self, text: str, default: Optional[str] = None) -> str:
        try:
            val = input(self._prompt_str(text, default)).strip()
        except EOFError:
            val = ""
        return val if val else (default or "")

    def confirm(self, text: str, default: bool = False) -> bool:
        val = self.ask(f"{text} (y/n)", "y" if default else "n").lower()
        return val in ("y", "yes", "д", "да")

    def choose(self, count: int, default_idx: int = 0, allow_text: bool = False, text: str = "Choice"):
        """0-based index, or the raw text when allow_text and input is not a number."""
        while True:
            raw = self.ask(text, str(default_idx + 1))
            try:
                idx = int(raw) - 1
                if 0 <= idx < count:
                    return idx
            except ValueError:
                if allow_text and raw:
                    return raw
            self.warn("Invalid choice")

    # ---- progress -------------------------------------------------------
    def progress(self):
        return _RichProgress(self.console) if (self.rich and self.color) else _PlainProgress()


class _RichProgress:
    def __init__(self, console):
        self.p = Progress(
            SpinnerColumn(style="magenta"),
            TextColumn("[bold]{task.description}"),
            BarColumn(bar_width=28, style="grey35", complete_style="magenta", finished_style="green"),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TextColumn("[dim]ETA"),
            TimeRemainingColumn(),
            TextColumn("[dim]{task.fields[note]}"),
            console=console,
            transient=False,
            redirect_stdout=True,
            redirect_stderr=True,
        )
        self.tasks = {}

    def __enter__(self):
        self.p.start()
        return self

    def __exit__(self, *a):
        self.p.stop()

    def add(self, name: str, description: str, total: int, note: str = ""):
        self.tasks[name] = self.p.add_task(description, total=max(total, 0), note=note)

    def update(self, name, completed=None, total=None, description=None, note=None):
        kw = {}
        if completed is not None:
            kw["completed"] = completed
        if total is not None:
            kw["total"] = max(total, 0)
        if description is not None:
            kw["description"] = description
        if note is not None:
            kw["note"] = note
        self.p.update(self.tasks[name], **kw)

    def finish(self, name: str):
        t = self.p.tasks[self.tasks[name]]
        self.p.update(self.tasks[name], completed=t.total or t.completed)


class _PlainProgress:
    """Line-based fallback: one status line, throttled to 4 Hz."""

    def __init__(self):
        self.state = {}
        self._last = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._render(force=True)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def add(self, name, description, total, note=""):
        self.state[name] = {"d": description, "c": 0, "t": total, "n": note}

    def update(self, name, completed=None, total=None, description=None, note=None):
        s = self.state[name]
        if completed is not None:
            s["c"] = completed
        if total is not None:
            s["t"] = total
        if description is not None:
            s["d"] = description
        if note is not None:
            s["n"] = note
        self._render()

    def finish(self, name):
        s = self.state[name]
        s["c"] = s["t"]
        self._render(force=True)

    def _render(self, force=False):
        now = time.time()
        if not force and now - self._last < 0.25:
            return
        self._last = now
        parts = []
        for s in self.state.values():
            pct = (100.0 * s["c"] / s["t"]) if s["t"] else 0.0
            parts.append(f"{s['d']} {s['c']}/{s['t']} ({pct:.0f}%) {s['n']}".rstrip())
        sys.stdout.write("\r" + " | ".join(parts)[:200].ljust(120))
        sys.stdout.flush()


class UIHandler(logging.Handler):
    """Logging handler rendering records through the UI (safe with live progress)."""

    def __init__(self, ui_obj):
        super().__init__()
        self.ui = ui_obj

    def emit(self, record: logging.LogRecord):
        try:
            self.ui.log_record(record)
        except Exception:
            self.handleError(record)


def mask_key(k: str) -> str:
    k = k or ""
    return f"••••{k[-4:]}" if len(k) > 4 else "****"


ui = UI()
