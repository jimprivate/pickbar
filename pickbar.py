#!/usr/bin/env python3
r"""pickbar: zero-dependency highlight-bar menus for the terminal.

One file, standard library only, Windows and POSIX, East-Asian-width aware
(CJK labels align correctly). Try the demo: python -m pickbar

Usage:
    from pickbar import pick
    i = pick(["Install", "Update", "Exit"], title="[ setup ]")
    # i = selected index (int), a value from `keys`, or None on cancel

    from pickbar import pick_multi
    idxs = pick_multi(["a.txt", "b.txt", "c/"], title="Select:")
    # idxs = selected indices in list order (may be empty), or None on cancel

    from pickbar import pick_dir
    path = pick_dir("Choose SOURCE:", allow_create=True)
    # path = chosen directory (str, may not exist when created/typed),
    # or None on cancel

Keys: Up/Down move (wraps), digits jump the bar (Enter confirms; typing
a number never selects directly, to avoid mis-picks), Home/End jump,
Enter select, Esc / q / 0 cancel. Extra letter hotkeys via keys={char: value}.

Falls back to the classic numbered input() prompt when stdin/stdout is not
a TTY (pipes, cron) or the terminal cannot do ANSI. Long lists scroll in a
viewport sized to the terminal.

https://github.com/jimprivate/pickbar
"""

import os
import shutil
import sys
import unicodedata
from pathlib import Path

__version__ = "0.1.0"
__all__ = ["pick", "pick_multi", "pick_dir"]

_WIN = os.name == "nt"
if _WIN:
    import ctypes
    import msvcrt
else:
    import select
    import termios
    import tty

_vt_ok = None


def _ansi_ok():
    """Enable VT processing on Windows; True if ANSI escapes will render."""
    global _vt_ok
    if _vt_ok is not None:
        return _vt_ok
    if not _WIN:
        _vt_ok = True
        return _vt_ok
    try:
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(h, ctypes.byref(mode)):
            # 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
            _vt_ok = bool(k32.SetConsoleMode(h, ctypes.c_uint32(mode.value | 0x0004)))
        else:
            _vt_ok = False
    except Exception:
        _vt_ok = False
    return _vt_ok


def _read1(fd, timeout=None):
    """Read one byte straight from the fd (bypasses Python's stdin buffer,
    which would make select() lie about pending escape-sequence bytes)."""
    if timeout is not None and not select.select([fd], [], [], timeout)[0]:
        return ""
    b = os.read(fd, 1)
    return b.decode("latin-1") if b else ""


def _getkey():
    """Blocking single-key read, normalized to 'up' / 'down' / 'home' /
    'end' / 'enter' / 'esc', or the literal character typed.
    POSIX: caller must already hold the terminal in cbreak mode."""
    if _WIN:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            return {"H": "up", "P": "down", "G": "home", "O": "end"}.get(ch2, "")
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x1b":
            return "esc"
        return ch

    fd = sys.stdin.fileno()
    ch = _read1(fd)
    if ch in ("\r", "\n"):
        return "enter"
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch != "\x1b":
        return ch
    # Bare Esc vs escape sequence: peek for a follow-up byte
    lead = _read1(fd, 0.05)
    if lead not in ("[", "O"):
        return "esc"
    # CSI: params end with a final byte in '@'..'~' (A, B, H, F, ~, ...)
    seq = ""
    while True:
        c = _read1(fd, 0.05)
        if not c:
            return ""
        seq += c
        if "@" <= c <= "~":
            break
    if seq[-1] == "~":
        return {"1": "home", "7": "home", "4": "end", "8": "end"}.get(seq[:-1], "")
    return {"A": "up", "B": "down", "H": "home", "F": "end"}.get(seq[-1], "")


def _dwidth(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _clip(s, width):
    if _dwidth(s) <= width:
        return s
    out, w = "", 0
    for c in s:
        cw = 2 if unicodedata.east_asian_width(c) in "WF" else 1
        if w + cw > width - 1:
            break
        out += c
        w += cw
    return out + "…"


def _pick_fallback(labels, title, keys, index):
    """Classic numbered prompt for non-TTY / no-ANSI environments.
    Blank Enter picks `index`, mirroring the interactive default."""
    print()
    if title:
        print(title)
    for i, label in enumerate(labels, 1):
        print(f"  {i}. {label}")
    print("  0. Cancel")
    while True:
        try:
            val = input(f"Select [{index + 1}]: ").strip()
        except EOFError:
            return None
        if val == "":
            return index
        low = val.lower()
        if low in keys:
            return keys[low]
        if val == "0" or low == "q":
            return None
        if val.isdigit() and 1 <= int(val) <= len(labels):
            return int(val) - 1
        print("Invalid.")


def pick(options, title=None, *, index=0, keys=None, footer=None):
    """Show a highlight-bar menu and return the chosen option's index.

    options: list of labels (anything str()-able).
    title:   printed once above the list.
    index:   initially highlighted row.
    keys:    optional {char: value} hotkeys; pressing char returns value.
    footer:  hint line under the list (default explains the keys).

    Returns int index, a `keys` value, or None on cancel (Esc / q / 0 /
    EOF). Ctrl-C raises KeyboardInterrupt as input() would.
    """
    labels = [str(o) for o in options]
    if not labels:
        return None
    keys = {str(k).lower(): v for k, v in (keys or {}).items()}
    index = max(0, min(index, len(labels) - 1))

    if not (sys.stdin.isatty() and sys.stdout.isatty() and _ansi_ok()):
        return _pick_fallback(labels, title, keys, index)

    idx = index
    hint = footer if footer is not None else "↑/↓ move · Enter select · Esc cancel"
    counts = [lab.count("\n") + 1 for lab in labels]  # physical lines per label
    drawn = 0  # physical lines currently owned below the title
    buf = ""   # typed digit accumulator (moves the bar; Enter confirms)

    if title:
        sys.stdout.write(title + "\n")

    # Hold cbreak for the whole menu: restoring the tty between keys would
    # let fast keypresses land in canonical mode and echo garbage (^[[A)
    # over the menu, or leak arrow sequences to the shell.
    old_tty = None
    if not _WIN:
        fd = sys.stdin.fileno()
        old_tty = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    try:
        sys.stdout.write("\x1b[?25l")
        while True:
            size = shutil.get_terminal_size((80, 24))
            budget = max(3, size.lines - 3)  # physical lines for the list
            width = max(20, size.columns - 1)

            # Grow the viewport around idx until the line budget is spent
            # (labels may span several physical lines each).
            top = bot = idx
            used = counts[idx]
            while True:
                grew = False
                if top > 0 and used + counts[top - 1] <= budget:
                    top -= 1
                    used += counts[top]
                    grew = True
                if bot + 1 < len(labels) and used + counts[bot + 1] <= budget:
                    bot += 1
                    used += counts[bot]
                    grew = True
                if not grew:
                    break

            out = []
            for row in range(top, bot + 1):
                # A single label taller than the budget would make the frame
                # taller than the terminal and break the cursor-up redraw.
                sub = labels[row].split("\n")[:budget]
                for j, part in enumerate(sub):
                    more = ""
                    if row == top and j == 0 and top > 0:
                        more = " ↑"
                    elif row == bot and j == len(sub) - 1 and bot + 1 < len(labels):
                        more = " ↓"
                    text = f" {row + 1:>2}. {part} " if j == 0 else part + " "
                    line = _clip(text, width - 2) + more
                    if row == idx:
                        line = "\x1b[7m" + line + "\x1b[0m"
                    out.append("\x1b[2K" + line)
            out.append("\x1b[2K\x1b[2m " + _clip(hint, width) + "\x1b[0m")
            if drawn:
                sys.stdout.write(f"\x1b[{drawn}A")
                if len(out) < drawn:
                    sys.stdout.write("\x1b[0J")
            sys.stdout.write("\n".join(out) + "\n")
            sys.stdout.flush()
            drawn = len(out)

            k = _getkey()
            if k == "up":
                idx = (idx - 1) % len(labels)
                buf = ""
            elif k == "down":
                idx = (idx + 1) % len(labels)
                buf = ""
            elif k == "home":
                idx = 0
                buf = ""
            elif k == "end":
                idx = len(labels) - 1
                buf = ""
            elif k == "enter":
                return idx
            elif k == "esc":
                return None
            elif k and k.lower() in keys:
                return keys[k.lower()]
            elif k == "q":
                return None
            elif k and k.isdigit():
                if k == "0" and not buf:
                    return None
                buf += k
                if 1 <= int(buf) <= len(labels):
                    idx = int(buf) - 1
                elif 1 <= int(k) <= len(labels):
                    buf = k
                    idx = int(k) - 1
                else:
                    buf = ""
    finally:
        if old_tty is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()


def _pick_multi_fallback(labels, title):
    """Numbered multi-select prompt for non-TTY / no-ANSI environments."""
    print()
    if title:
        print(title)
    for i, label in enumerate(labels, 1):
        print(f"  {i}. {label}")
    print("  0. Cancel")
    while True:
        try:
            val = input("Select (e.g. 1 3 5 · 'a' = all): ").strip()
        except EOFError:
            return None
        low = val.lower()
        if val == "0" or low == "q":
            return None
        if low == "a":
            return list(range(len(labels)))
        toks = val.replace(",", " ").split()
        if toks and all(t.isdigit() and 1 <= int(t) <= len(labels) for t in toks):
            return sorted({int(t) - 1 for t in toks})
        print("Invalid.")


def pick_multi(options, title=None, *, footer=None):
    """Highlight-bar multi-select; single-line labels only.

    Space toggles the highlighted row (and advances), 'a' toggles all,
    Enter confirms, Esc / q cancels.

    Returns the selected indices in list order (possibly empty), or None
    on cancel.
    """
    labels = [str(o) for o in options]
    if not labels:
        return []
    if not (sys.stdin.isatty() and sys.stdout.isatty() and _ansi_ok()):
        return _pick_multi_fallback(labels, title)

    idx = 0
    chosen = set()
    drawn = 0
    if title:
        sys.stdout.write(title + "\n")

    fd = sys.stdin.fileno()
    old_tty = None
    if not _WIN:
        old_tty = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    try:
        sys.stdout.write("\x1b[?25l")
        while True:
            size = shutil.get_terminal_size((80, 24))
            width = max(20, size.columns - 1)
            budget = max(3, size.lines - 3)
            top = max(0, min(idx - budget // 2, len(labels) - budget))
            rows = range(top, min(top + budget, len(labels)))

            out = []
            for row in rows:
                more = ""
                if row == top and top > 0:
                    more = " ↑"
                elif row == rows[-1] and rows[-1] + 1 < len(labels):
                    more = " ↓"
                mark = "x" if row in chosen else " "
                line = _clip(f" [{mark}] {labels[row]} ", width - 2) + more
                if row == idx:
                    line = "\x1b[7m" + line + "\x1b[0m"
                out.append("\x1b[2K" + line)
            if footer is not None:
                hint = footer
            else:
                hint = "Space toggle · a all · Enter confirm · Esc cancel"
                if chosen:
                    hint = f"{len(chosen)} selected · " + hint
            out.append("\x1b[2K\x1b[2m " + _clip(hint, width) + "\x1b[0m")

            if drawn:
                sys.stdout.write(f"\x1b[{drawn}A")
                if len(out) < drawn:
                    sys.stdout.write("\x1b[0J")
            sys.stdout.write("\n".join(out) + "\n")
            sys.stdout.flush()
            drawn = len(out)

            k = _getkey()
            if k == "up":
                idx = (idx - 1) % len(labels)
            elif k == "down":
                idx = (idx + 1) % len(labels)
            elif k == "home":
                idx = 0
            elif k == "end":
                idx = len(labels) - 1
            elif k == " ":
                if idx in chosen:
                    chosen.discard(idx)
                else:
                    chosen.add(idx)
                if idx + 1 < len(labels):
                    idx += 1
            elif k in ("a", "A"):
                chosen = set() if len(chosen) == len(labels) else set(range(len(labels)))
            elif k == "enter":
                return sorted(chosen)
            elif k in ("esc", "q"):
                return None
    finally:
        if old_tty is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()


def _ask_line(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _utf8_tail(lead):
    """Continuation-byte count for a UTF-8 lead byte (0 = ASCII/invalid)."""
    if 0xC2 <= lead < 0xE0:
        return 1
    if 0xE0 <= lead < 0xF0:
        return 2
    if 0xF0 <= lead < 0xF5:
        return 3
    return 0


def _pick_typed(labels, title=None):
    """Highlight-bar menu with type-to-filter, for pick_dir.

    Typing filters the list (case-insensitive substring); a query starting
    with '/' or '~' switches to jump-to-path. Digits and letters are always
    literal input here; no digit-jump / hotkeys / q-cancel like pick().

    Returns ("pick", original_index), ("path", typed_text), or None on
    cancel (Esc with an empty query). TTY + ANSI only; callers must fall
    back to pick() otherwise.
    """
    if title:
        sys.stdout.write(title + "\n")

    pos = 0        # position within the filtered view
    query = ""
    drawn = 0
    fd = sys.stdin.fileno()
    old_tty = None
    if not _WIN:
        old_tty = termios.tcgetattr(fd)
        tty.setcbreak(fd)

    try:
        sys.stdout.write("\x1b[?25l")
        while True:
            size = shutil.get_terminal_size((80, 24))
            width = max(20, size.columns - 1)
            budget = max(3, size.lines - 4)

            pathmode = query[:1] in ("/", "~")
            if pathmode:
                visible = []
            elif query:
                q = query.lower()
                visible = [i for i, l in enumerate(labels) if q in l.lower()]
            else:
                visible = list(range(len(labels)))
            if pos >= len(visible):
                pos = max(0, len(visible) - 1)

            top = max(0, min(pos - budget // 2, len(visible) - budget))
            rows = visible[top:top + budget]

            out = []
            for vi, i in enumerate(rows, start=top):
                more = ""
                if vi == top and top > 0:
                    more = " ↑"
                elif vi == top + len(rows) - 1 and top + len(rows) < len(visible):
                    more = " ↓"
                line = _clip(" " + labels[i] + " ", width - 2) + more
                if vi == pos:
                    line = "\x1b[7m" + line + "\x1b[0m"
                out.append("\x1b[2K" + line)

            if pathmode:
                out.append("\x1b[2K → go to: " + _clip(query, width - 11))
                status = "Enter jump · Backspace edit · Esc clear"
            elif query:
                miss = "" if visible else "   (no match)"
                out.append("\x1b[2K filter: " + _clip(query, width - 11) + miss)
                status = "Enter select · Backspace edit · Esc clear"
            else:
                status = "type to filter · / or ~ jumps to path · ↑/↓ · Enter · Esc"
            out.append("\x1b[2K\x1b[2m " + _clip(status, width) + "\x1b[0m")

            if drawn:
                sys.stdout.write(f"\x1b[{drawn}A")
                if len(out) < drawn:
                    sys.stdout.write("\x1b[0J")
            sys.stdout.write("\n".join(out) + "\n")
            sys.stdout.flush()
            drawn = len(out)

            k = _getkey()
            if k == "up" and visible:
                pos = (pos - 1) % len(visible)
            elif k == "down" and visible:
                pos = (pos + 1) % len(visible)
            elif k == "home":
                pos = 0
            elif k == "end":
                pos = max(0, len(visible) - 1)
            elif k == "enter":
                if pathmode:
                    return ("path", query)
                if visible:
                    return ("pick", visible[pos])
            elif k == "esc":
                if query:
                    query = ""
                    pos = 0
                else:
                    return None
            elif k in ("\x7f", "\x08"):
                query = query[:-1]
                pos = 0
            elif k and len(k) == 1 and k >= " ":
                if not _WIN and ord(k) >= 0x80:
                    # _read1 delivers raw bytes as latin-1; reassemble UTF-8
                    b = bytes([ord(k)])
                    for _ in range(_utf8_tail(ord(k))):
                        c = _read1(fd, 0.05)
                        if not c:
                            break
                        b += bytes([ord(c)])
                    try:
                        k = b.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                query += k
                pos = 0
    finally:
        if old_tty is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_tty)
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()


def pick_dir(title=None, start=None, allow_create=False):
    """Browse the filesystem with the highlight-bar menu; return a directory.

    On a TTY, typing filters the entries and a leading '/' or '~' jumps
    straight to that path (see _pick_typed); otherwise pick()'s numbered
    fallback is used.

    title:        printed above the menu at every level.
    start:        initial directory (default: cwd).
    allow_create: offer "new subdirectory here"; the directory is NOT
                  created, the would-be path is just returned (callers
                  mkdir on apply).

    Returns the chosen path as str (existing dirs are resolved; created or
    manually typed paths may not exist), or None on cancel.
    """
    cur = Path(start or Path.cwd()).resolve()
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and _ansi_ok()
    while True:
        try:
            subs = sorted(
                (p for p in cur.iterdir() if p.is_dir()),
                key=lambda p: (p.name.startswith("."), p.name.lower()),
            )
        except OSError as e:
            print(f"  [!] Cannot list {cur}: {e}")
            subs = []

        labels = ["[ Select this directory ]"]
        actions = ["select"]
        if cur.parent != cur:
            labels.append("../")
            actions.append("up")
        for p in subs:
            labels.append(p.name + "/")
            actions.append(p)
        if allow_create:
            labels.append("[ New subdirectory here… ]")
            actions.append("new")
        labels.append("[ Type a path manually… ]")
        actions.append("manual")

        head = f"{title}\n  {cur}" if title else f"  {cur}"
        if interactive:
            r = _pick_typed(labels, title=head)
            if r is None:
                return None
            kind, val = r
            if kind == "path":
                p = Path(val).expanduser()
                if p.is_dir():
                    cur = p.resolve()
                else:
                    print(f"  [!] Not a directory: {p}")
                continue
            act = actions[val]
        else:
            i = pick(labels, title=head)
            if i is None:
                return None
            act = actions[i]
        if act == "select":
            return str(cur)
        if act == "up":
            cur = cur.parent
        elif act == "new":
            name = _ask_line("  New directory name: ")
            if name:
                return str(cur / name)
        elif act == "manual":
            # Relative input is anchored to the directory being browsed,
            # not the process cwd; what's on screen is what you get.
            path = _ask_line("  Path: ")
            if path:
                p = Path(path).expanduser()
                return str(p if p.is_absolute() else cur / p)
        else:
            cur = act


if __name__ == "__main__":
    choice = pick(["Install", "Update", "Uninstall", "Quit"],
                  title="[ pickbar demo · pick ]")
    print(f"pick() -> {choice!r}")
    if choice is not None and choice != 3:
        sel = pick_multi(["alpha.txt", "beta.txt", "gamma/", "中文標籤.md"],
                         title="[ pickbar demo · pick_multi ]")
        print(f"pick_multi() -> {sel!r}")
        path = pick_dir("[ pickbar demo · pick_dir ]", allow_create=True)
        print(f"pick_dir() -> {path!r}")
