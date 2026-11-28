"""Native terminal display and platform console handling."""

import os
import sys

from pdf2zh_server.tasks.progress import MAIN_PROGRESS_RE, STEP_PROGRESS_RE

_ansi_support = None


def _terminal_ansi_ok():
    """Lazy: macOS/Linux 恒 True; Windows 尝试启用 VT 处理。"""
    global _ansi_support
    if _ansi_support is not None:
        return _ansi_support
    import platform

    if platform.system() != "Windows":
        _ansi_support = True
    else:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 4)
                _ansi_support = True
            else:
                _ansi_support = False
        except Exception:
            _ansi_support = False
    return _ansi_support


class _ProgressLine:
    """One-line progress that refreshes in place (or space-pads on old cmd.exe)."""

    def __init__(self):
        self._prev_len = 0
        self._prev_msg = ""
        self._active = False

    def write(self, text, message):
        if message != self._prev_msg and self._active:
            sys.stdout.write("\n")
            sys.stdout.flush()
        if _terminal_ansi_ok():
            sys.stdout.write(f"\r\x1b[K{text}")
        else:
            padding = " " * max(0, self._prev_len - len(text))
            sys.stdout.write(f"\r{text}{padding}")
        sys.stdout.flush()
        self._prev_len = len(text)
        self._prev_msg = message
        self._active = True

    def finish(self):
        if self._active:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._active = False


WINDOWS_MONITOR_INTERVAL = 0.05

WINDOWS_CONSOLE_SCAN_ROWS = 220


def _windows_visible_console_size():
    """Visible window size, not the (often much wider) screen buffer."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [
                ("Left", wintypes.SHORT),
                ("Top", wintypes.SHORT),
                ("Right", wintypes.SHORT),
                ("Bottom", wintypes.SHORT),
            ]

        class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
            _fields_ = [
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD),
                ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD),
            ]

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        if handle in (None, 0, ctypes.c_void_p(-1).value):
            return None
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        if not kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi)):
            return None
        win = csbi.srWindow
        width = int(win.Right - win.Left + 1)
        height = int(win.Bottom - win.Top + 1)
        if width > 0 and height > 0:
            return (width, height)
    except Exception:
        return None
    return None


def _detect_terminal_size(default_cols=80, default_rows=24):
    """Size of the terminal the user actually sees."""
    cols, rows = (default_cols, default_rows)
    visible = _windows_visible_console_size()
    if visible:
        cols, rows = visible
    else:
        try:
            size = os.get_terminal_size()
            if size.columns > 0:
                cols = size.columns
            if size.lines > 0:
                rows = size.lines
        except (OSError, ValueError, AttributeError):
            pass
    return (max(40, int(cols)), max(10, int(rows)))


def _apply_terminal_size_env(env, cols, rows):
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)


def _child_terminal_size(cols, rows):
    return (max(40, int(cols) - 1), max(10, int(rows)))


def _monitor_windows_console_translate_progress(on_progress, stop_event):
    """
    Windows-only monitor:
    Read console buffer and parse only "translate ... x/y".
    This keeps native progress bars untouched while enabling SSE updates.
    """
    if on_progress is None:
        return
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return
    STD_OUTPUT_HANDLE = -11
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [
            ("Left", wintypes.SHORT),
            ("Top", wintypes.SHORT),
            ("Right", wintypes.SHORT),
            ("Bottom", wintypes.SHORT),
        ]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", COORD),
            ("dwCursorPosition", COORD),
            ("wAttributes", wintypes.WORD),
            ("srWindow", SMALL_RECT),
            ("dwMaximumWindowSize", COORD),
        ]

    try:
        kernel32 = ctypes.windll.kernel32
        get_std_handle = kernel32.GetStdHandle
        get_std_handle.argtypes = [wintypes.DWORD]
        get_std_handle.restype = wintypes.HANDLE
        get_csbi = kernel32.GetConsoleScreenBufferInfo
        get_csbi.restype = wintypes.BOOL
        read_console = kernel32.ReadConsoleOutputCharacterW
        read_console.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            COORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        read_console.restype = wintypes.BOOL
    except Exception as e:
        return
    handle = get_std_handle(STD_OUTPUT_HANDLE)
    if handle in (None, 0, INVALID_HANDLE_VALUE):
        return
    locked_total = None
    last_curr = None
    last_row = None
    last_step = None
    idle_ticks = 0
    last_error = ""
    while not stop_event.is_set():
        try:
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if not get_csbi(handle, ctypes.byref(csbi)):
                print(
                    "⚠️ 无法读取 Windows 控制台缓冲区（stdout 可能已重定向）；控制台进度监视已停止，翻译进程继续运行。"
                )
                break
            width = max(int(csbi.dwSize.X), 1)
            buffer_rows = max(int(csbi.dwSize.Y), 1)
            cursor_y = int(csbi.dwCursorPosition.Y)
            start_row = max(0, cursor_y - WINDOWS_CONSOLE_SCAN_ROWS)
            end_row = min(buffer_rows - 1, cursor_y + 2)
            if end_row < start_row:
                start_row, end_row = (
                    0,
                    min(buffer_rows - 1, WINDOWS_CONSOLE_SCAN_ROWS),
                )
            pair_candidates = []
            latest_step = None
            latest_step_row = -1
            translate_line_sample = None
            for row in range(start_row, end_row + 1):
                buf = ctypes.create_unicode_buffer(width)
                chars_read = wintypes.DWORD(0)
                ok = read_console(
                    handle, buf, width, COORD(0, row), ctypes.byref(chars_read)
                )
                if not ok or chars_read.value <= 0:
                    continue
                line = buf.value[: chars_read.value].strip()
                if not line:
                    continue
                if translate_line_sample is None and "translate" in line.lower():
                    translate_line_sample = line[:220]
                step_m = STEP_PROGRESS_RE.search(line)
                if step_m and row >= latest_step_row:
                    latest_step = step_m.group(1).strip()
                    latest_step_row = row
                m = MAIN_PROGRESS_RE.search(line)
                if not m:
                    continue
                curr, total = (int(m.group(1)), int(m.group(2)))
                if total <= 0:
                    continue
                if locked_total is not None and total != locked_total:
                    continue
                pair_candidates.append((row, curr, total))
            if pair_candidates:
                idle_ticks = 0
                if locked_total is None:
                    max_total = max((c[2] for c in pair_candidates))
                    pair_candidates = [c for c in pair_candidates if c[2] == max_total]
                    pair_candidates.sort(
                        key=lambda c: (abs(c[0] - cursor_y), -c[0], -c[1])
                    )
                    row, curr, total = pair_candidates[0]
                    locked_total = total
                else:

                    def _rank(candidate):
                        row = candidate[0]
                        dist_prev = (
                            abs(row - last_row)
                            if last_row is not None
                            else abs(row - cursor_y)
                        )
                        dist_cursor = abs(row - cursor_y)
                        return (dist_prev, dist_cursor, -row)

                    pair_candidates.sort(key=_rank)
                    row, curr, total = pair_candidates[0]
                if last_curr is None or curr >= last_curr:
                    last_row = row
                    if last_curr is None or curr != last_curr:
                        last_curr = curr
                        pct = 99 if curr >= total else int(curr / total * 100)
                        on_progress(
                            {
                                "progress": pct,
                                "status": "running",
                                "message": f"translate {curr}/{total}",
                            }
                        )
            else:
                idle_ticks += 1
                if idle_ticks % 40 == 0:
                    pass
            if latest_step and latest_step != last_step:
                last_step = latest_step
                on_progress({"status": "running", "message": latest_step})
        except Exception as e:
            err_text = str(e)
            if err_text != last_error:
                last_error = err_text
        stop_event.wait(WINDOWS_MONITOR_INTERVAL)


def _guard_windows_console_min_width(stop_event, min_cols):
    """
    Restore the window width we started with if the user shrinks it mid-run.
    Do not force a fake 160-column window: that only widens the buffer and
    makes rich wrap even harder on the visible area.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return
    STD_OUTPUT_HANDLE = -11
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class COORD(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [
            ("Left", wintypes.SHORT),
            ("Top", wintypes.SHORT),
            ("Right", wintypes.SHORT),
            ("Bottom", wintypes.SHORT),
        ]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", COORD),
            ("dwCursorPosition", COORD),
            ("wAttributes", wintypes.WORD),
            ("srWindow", SMALL_RECT),
            ("dwMaximumWindowSize", COORD),
        ]

    try:
        kernel32 = ctypes.windll.kernel32
        get_std_handle = kernel32.GetStdHandle
        get_std_handle.argtypes = [wintypes.DWORD]
        get_std_handle.restype = wintypes.HANDLE
        get_csbi = kernel32.GetConsoleScreenBufferInfo
        get_csbi.restype = wintypes.BOOL
        set_buffer_size = kernel32.SetConsoleScreenBufferSize
        set_buffer_size.argtypes = [wintypes.HANDLE, COORD]
        set_buffer_size.restype = wintypes.BOOL
        set_window_info = kernel32.SetConsoleWindowInfo
        set_window_info.argtypes = [
            wintypes.HANDLE,
            wintypes.BOOL,
            ctypes.POINTER(SMALL_RECT),
        ]
        set_window_info.restype = wintypes.BOOL
    except Exception:
        return
    handle = get_std_handle(STD_OUTPUT_HANDLE)
    if handle in (None, 0, INVALID_HANDLE_VALUE):
        return
    while not stop_event.is_set():
        try:
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            if not get_csbi(handle, ctypes.byref(csbi)):
                break
            win = csbi.srWindow
            width = int(win.Right - win.Left + 1)
            height = int(win.Bottom - win.Top + 1)
            if width < min_cols:
                max_w = max(int(csbi.dwMaximumWindowSize.X) or min_cols, 1)
                target_width = min(int(min_cols), max_w)
                if width >= target_width:
                    stop_event.wait(0.08)
                    continue
                target_height = max(int(csbi.dwSize.Y), height)
                target_buffer_width = max(int(csbi.dwSize.X), target_width)
                set_buffer_size(handle, COORD(target_buffer_width, target_height))
                new_top = max(0, min(int(win.Top), target_height - height))
                new_rect = SMALL_RECT(
                    0, new_top, target_width - 1, new_top + height - 1
                )
                set_window_info(handle, True, ctypes.byref(new_rect))
        except Exception:
            pass
        stop_event.wait(0.08)
