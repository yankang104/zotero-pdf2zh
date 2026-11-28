#!/bin/bash

PROJECT_PATH="${ZOTERO_PDF2ZH_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
LOG_DIR="$PROJECT_PATH/logs"
MONITOR_LOG="$LOG_DIR/monitor.log"
START_SCRIPT="$PROJECT_PATH/integrations/macos/start_server.sh"
SERVER_PORT=8888
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$MONITOR_LOG"
}

notify() {
    local title="$1"
    local message="$2"
    local notifier
    notifier=$(command -v terminal-notifier)
    if [ -n "$notifier" ]; then
        "$notifier" -title "$title" -message "$message" -group "zotero-pdf2zh" > /dev/null 2>&1 &
    else
        osascript -e 'on run argv' \
            -e 'display notification (item 2 of argv) with title (item 1 of argv)' \
            -e 'end run' "$title" "$message" > /dev/null 2>&1 &
    fi
    log "通知: $title - $message"
}

is_server_running() {
    /bin/bash "$START_SCRIPT" status > /dev/null 2>&1
}

has_active_tasks() {
    local response
    if ! response=$(curl --fail --silent --show-error --max-time 5 "http://127.0.0.1:$SERVER_PORT/api/tasks"); then
        log "暂时无法读取任务状态，本轮保留服务。"
        return 0
    fi
    printf '%s' "$response" | grep -Eq '"active"[[:space:]]*:[[:space:]]*true'
}

if pgrep -f "Zotero.app" > /dev/null; then
    if ! is_server_running; then
        log "Zotero 正在运行，启动主 Server。"
        if /bin/bash "$START_SCRIPT" start >> "$MONITOR_LOG" 2>&1; then
            notify "Zotero PDF2zh" "PDF 翻译服务进程已启动"
        else
            notify "Zotero PDF2zh" "翻译服务启动失败，请查看 logs/server.log"
        fi
    fi
elif is_server_running; then
    if pgrep -f '[t]ranslate_pdf_client[.]py' > /dev/null || has_active_tasks; then
        log "Zotero 已关闭，等待当前翻译或结果下载结束。"
    else
        log "Zotero 已关闭且没有活动任务，停止主 Server。"
        /bin/bash "$START_SCRIPT" stop >> "$MONITOR_LOG" 2>&1
        notify "Zotero PDF2zh" "PDF 翻译服务已停止"
    fi
fi
