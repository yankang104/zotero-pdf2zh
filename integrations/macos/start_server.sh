#!/bin/bash

# All macOS entry points use this lifecycle and the same main Server process.
PROJECT_PATH="${ZOTERO_PDF2ZH_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
SERVER_PATH="$PROJECT_PATH/server"
LOG_DIR="$PROJECT_PATH/logs"
SERVER_LOG="$LOG_DIR/server.log"
PID_FILE="$LOG_DIR/zotero_python.pid"
CONDA_PATH="/opt/anaconda3"
PYTHON_EXE="${ZOTERO_PDF2ZH_PYTHON:-$CONDA_PATH/envs/zotero-pdf2zh-next-venv/bin/python}"
SERVER_PORT=8888
mkdir -p "$LOG_DIR"

is_server_running() {
    [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1
}

stop_server() {
    if is_server_running; then
        local pid
        pid=$(cat "$PID_FILE")
        echo "正在停止服务器 (PID: $pid)..."
        kill "$pid" || return 1
        while ps -p "$pid" > /dev/null 2>&1; do
            sleep 1
        done
    fi
    rm -f "$PID_FILE"
}

start_server() {
    if is_server_running; then
        echo "服务器已经运行 (PID: $(cat "$PID_FILE"))"
        return 0
    fi
    rm -f "$PID_FILE"
    if lsof -iTCP:"$SERVER_PORT" -sTCP:LISTEN -t > /dev/null 2>&1; then
        echo "端口 $SERVER_PORT 已被占用，请使用已有主 Server 或先停止占用进程。"
        return 1
    fi
    cd "$SERVER_PATH" || return 1
    export PATH="$CONDA_PATH/bin:$PATH"
    echo "启动 Zotero PDF2zh 主 Server，日志：$SERVER_LOG"
    nohup "$PYTHON_EXE" server.py \
        --port "$SERVER_PORT" \
        --enable_venv True \
        --env_tool conda \
        --skip_install True \
        --check_update False \
        > "$SERVER_LOG" 2>&1 &
    local server_pid=$!
    echo "$server_pid" > "$PID_FILE"
    sleep 2
    if ps -p "$server_pid" > /dev/null 2>&1; then
        echo "服务器进程已启动 (PID: $server_pid)"
    else
        rm -f "$PID_FILE"
        echo "服务器启动失败，最近日志："
        tail -n 20 "$SERVER_LOG"
        return 1
    fi
}

case "${1:-start}" in
    start) start_server ;;
    stop) stop_server ;;
    restart) stop_server && start_server ;;
    status)
        if is_server_running; then
            echo "服务器正在运行 (PID: $(cat "$PID_FILE"))"
        else
            echo "这套脚本管理的服务器未运行"
            exit 1
        fi
        ;;
    *) echo "用法: $0 {start|stop|restart|status}"; exit 1 ;;
esac
