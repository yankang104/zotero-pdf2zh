"""Run the chosen engine process and stream output to its native terminal."""

import codecs
import os
import select
import subprocess
import sys
import threading

from pdf2zh_server.engines.console import (
    _apply_terminal_size_env,
    _child_terminal_size,
    _detect_terminal_size,
    _guard_windows_console_min_width,
    _monitor_windows_console_translate_progress,
)
from pdf2zh_server.engines.next_runtime.deepseek import prepare_deepseek_runtime_command
from pdf2zh_server.engines.next_runtime.launcher import prepare_table_runtime_command
from pdf2zh_server.environment.discovery import managed_python_env
from pdf2zh_server.tasks.progress import (
    _record_engine_text,
    recent_engine_output,
    report_progress,
)


def _decode_pty_utf8(data, leftover):
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    text = decoder.decode(leftover + data, final=False)
    return text, decoder.getstate()[0]


def _write_pty_chunk(data, leftover, on_progress):
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except Exception:
        text, leftover = _decode_pty_utf8(data, leftover)
        sys.stdout.write(text)
        sys.stdout.flush()
        report_progress(text, on_progress)
        _record_engine_text(text)
        return leftover
    text, leftover = _decode_pty_utf8(data, leftover)
    report_progress(text, on_progress)
    _record_engine_text(text)
    return leftover


def execute_with_progress(cmd, task_id, args, env_manager, on_progress=None):
    """Execute translation command and update task progress in real time."""
    final_cmd = cmd
    final_env = os.environ.copy()
    final_env["PYTHONUNBUFFERED"] = "1"
    final_env["FORCE_COLOR"] = "1"
    final_env["FORCE_TERMINAL"] = "1"
    final_env.pop("NO_COLOR", None)
    final_env["TERM"] = "xterm-256color"

    cols, rows = _detect_terminal_size()
    child_cols, child_rows = _child_terminal_size(cols, rows)
    _apply_terminal_size_env(final_env, child_cols, child_rows)

    if args.enable_venv and env_manager:
        venv_cmd, venv_env = env_manager.get_command_and_env(cmd)
        final_cmd = venv_cmd
        final_env.update(venv_env)
        final_env = managed_python_env(final_env)
        # venv env is copied from os.environ and would undo COLUMNS/LINES.
        _apply_terminal_size_env(final_env, child_cols, child_rows)

    # DeepSeek V4 is special: the plugin stores the user's choice in generic
    # extraData, while pdf2zh_next 2.9+ exposes that choice as explicit CLI
    # flags. Validate the exact runtime that will be executed, then add those
    # flags before any translation/API request begins.
    final_cmd = prepare_deepseek_runtime_command(final_cmd, final_env)
    final_cmd = prepare_table_runtime_command(final_cmd)

    print(f"[execute_with_progress] {' '.join(final_cmd)}\n")

    if sys.platform != "win32":
        _execute_with_pty(final_cmd, final_env, on_progress, child_cols, child_rows)
    else:
        _execute_with_inherit(final_cmd, final_env, on_progress, cols)


def _execute_with_pty(final_cmd, final_env, on_progress, cols, rows):
    """macOS/Linux: run command in PTY and parse progress from stream."""
    import pty

    master_fd, slave_fd = pty.openpty()

    try:
        import fcntl
        import struct
        import termios

        winsize = struct.pack("HHHH", int(rows), int(cols), 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass

    process = subprocess.Popen(
        final_cmd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=final_env,
        bufsize=0,
        close_fds=True,
    )
    os.close(slave_fd)
    leftover = b""

    try:
        while True:
            readable, _, _ = select.select([master_fd], [], [], 0.1)
            if master_fd in readable:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    leftover = _write_pty_chunk(data, leftover, on_progress)
                except OSError:
                    break

            if process.poll() is not None:
                try:
                    import fcntl as _fcntl

                    fl = _fcntl.fcntl(master_fd, _fcntl.F_GETFL)
                    _fcntl.fcntl(master_fd, _fcntl.F_SETFL, fl | os.O_NONBLOCK)
                    while True:
                        data = os.read(master_fd, 4096)
                        if not data:
                            break
                        leftover = _write_pty_chunk(data, leftover, on_progress)
                except Exception:
                    pass
                break

        os.close(master_fd)
        return_code = process.wait()
        if return_code != 0:
            raise subprocess.CalledProcessError(
                return_code, final_cmd, stderr=recent_engine_output()
            )

    except Exception:
        if process.poll() is None:
            process.kill()
        try:
            os.close(master_fd)
        except Exception:
            pass
        raise


def _execute_with_inherit(final_cmd, final_env, on_progress, cols):
    """
    Windows: inherit stdout/stderr so terminal keeps native multi-progress UI.
    Progress parsing is done by a side monitor reading console buffer.
    """
    # stdout 保持直通以保留原生进度条; stderr 捕获后原样转发终端,
    # 同时留一份尾部用于错误解读(引擎报错都走 stderr)。
    process = subprocess.Popen(
        final_cmd,
        stdout=None,
        stderr=subprocess.PIPE,
        env=final_env,
        bufsize=0,
        text=False,
    )

    def _drain_stderr():
        try:
            for raw in iter(process.stderr.readline, b""):
                line = raw.decode("utf-8", errors="replace")
                sys.stderr.write(line)
                sys.stderr.flush()
                _record_engine_text(line)
        except Exception:
            pass

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # _debug_progress_log("EXECUTE_START", on_progress=on_progress, cmd=" ".join(final_cmd))

    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=_monitor_windows_console_translate_progress,
        args=(on_progress, stop_event),
        daemon=True,
    )
    monitor_thread.start()

    width_guard_thread = threading.Thread(
        target=_guard_windows_console_min_width,
        args=(stop_event, cols),
        daemon=True,
    )
    width_guard_thread.start()

    return_code = None
    try:
        return_code = process.wait()
    finally:
        stop_event.set()
        monitor_thread.join(timeout=1.5)
        width_guard_thread.join(timeout=1.0)
        stderr_thread.join(timeout=2.0)

    # _debug_progress_log("EXECUTE_END", on_progress=on_progress, return_code=return_code)

    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code, final_cmd, stderr=recent_engine_output()
        )
