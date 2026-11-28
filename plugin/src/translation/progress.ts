import { getPref, isTrue } from "../utils/prefs";
import { getString } from "../utils/locale";
import type { JobProgressUpdate, TranslationNotice } from "./types";

const shownNotices = new Set<string>();

export function showTranslationNotice(notice: TranslationNotice): void {
    if (notice.message === null) {
        shownNotices.delete(notice.key);
        return;
    }
    if (shownNotices.has(notice.key)) return;
    shownNotices.add(notice.key);
    ztoolkit.log("[server warning]", notice.message);
    new ztoolkit.ProgressWindow(getString("operation-progress-title"), {
        closeOtherProgressWindows: false,
    })
        .createLine({ text: notice.message, type: notice.type || "default" })
        .show();
}

export function operationActionLabel(endpoint: string): string {
    if (endpoint === "crop") {
        return getString("operation-action-crop");
    }
    if (endpoint === "compare") {
        return getString("operation-action-compare");
    }
    if (endpoint === "crop-compare") {
        return getString("operation-action-crop-compare");
    }
    return getString("operation-action-translate");
}

export function formatJobProgressText(update: JobProgressUpdate): string {
    const action = operationActionLabel(update.endpoint);
    let text = "";
    switch (update.phase) {
        case "submitting":
            text = getString("operation-progress-submitting", {
                args: { fileName: update.fileName },
            });
            break;
        case "accepted":
            text = getString("operation-progress-accepted", {
                args: { fileName: update.fileName, action },
            });
            break;
        case "running": {
            const parts: string[] = [];
            if (
                typeof update.percent === "number" &&
                Number.isFinite(update.percent) &&
                update.percent > 0
            ) {
                parts.push(`${Math.round(update.percent)}%`);
            }
            if (update.detail) {
                parts.push(update.detail);
            }
            text = getString("operation-progress-running", {
                args: {
                    fileName: update.fileName,
                    action,
                    suffix: parts.length ? ` · ${parts.join(" · ")}` : "",
                },
            });
            break;
        }
        case "importing":
            text = getString("operation-progress-importing", {
                args: { fileName: update.fileName },
            });
            break;
        case "file-done":
            text = getString("operation-progress-file-done", {
                args: { fileName: update.fileName },
            });
            break;
        case "file-failed":
            text = getString("operation-progress-file-failed", {
                args: {
                    fileName: update.fileName,
                    message: shortProgressError(
                        update.error || getString("operation-error-unknown"),
                    ),
                },
            });
            break;
    }
    return text;
}

export function shortProgressError(message: string): string {
    const compact = message.replace(/\s+/g, " ").trim();
    if (compact.length <= 80) {
        return compact;
    }
    return `${compact.slice(0, 77)}...`;
}

export function jobProgressPercent(update: JobProgressUpdate): number {
    const fileFraction = (() => {
        if (update.phase === "submitting") {
            return 0.05;
        }
        if (update.phase === "accepted") {
            return 0.12;
        }
        if (update.phase === "running") {
            const raw =
                typeof update.percent === "number" &&
                Number.isFinite(update.percent)
                    ? Math.min(Math.max(update.percent, 0), 100)
                    : 0;
            return 0.12 + (raw / 100) * 0.73;
        }
        if (update.phase === "importing") {
            return 0.9;
        }
        return 1;
    })();
    return Math.round(
        ((update.current - 1 + fileFraction) / update.total) * 100,
    );
}

/**
 * 让 Zotero 进度窗口重新按内容自适应高度。
 * Zotero 只在窗口创建/移动时 sizeToContent, 行文字增长(长文件名换行、
 * 错误信息追加)后窗口不会跟着长, 底部内容会被裁掉。
 */
function resizeProgressWindow(helper: any): void {
    try {
        const line = helper?.lines?.[0];
        const domWindow = (line as any)?._hbox?.ownerGlobal;
        if (domWindow?.sizeToContent) {
            domWindow.sizeToContent();
        }
    } catch {
        // 内部结构变化时静默跳过, 不影响翻译流程
    }
}

export class JobProgressPopup {
    private static shared: {
        window: any;
        lineCount: number;
        batches: number;
        closeToken: number;
    } | null = null;

    private window: any;
    private summaryIdx: number;
    private fileIdx: number[];
    private total: number;
    private done = 0;
    private finishedFiles = new Set<number>();
    private enabled: boolean;

    static shouldShow(): boolean {
        const raw = getPref("showProgress");
        if (raw === undefined || raw === null || raw === "") {
            return true;
        }
        return isTrue(raw);
    }

    static open(fileNames: string[]): JobProgressPopup {
        return new JobProgressPopup(fileNames);
    }

    private constructor(fileNames: string[]) {
        this.enabled = JobProgressPopup.shouldShow();
        this.total = fileNames.length;
        this.fileIdx = [];
        this.summaryIdx = 0;
        if (!this.enabled) {
            this.window = null;
            return;
        }
        const firstOpen = !JobProgressPopup.shared?.window;
        const shared = JobProgressPopup.ensureWindow();
        this.window = shared.window;
        shared.batches += 1;
        shared.closeToken += 1;
        this.summaryIdx = shared.lineCount;
        this.createLine({
            text: getString("operation-batch-started", {
                args: { count: this.total },
            }),
            type: "default",
            progress: 0,
        });
        this.fileIdx = fileNames.map((fileName) => {
            const idx = shared.lineCount;
            this.createLine({
                text: getString("operation-progress-waiting", {
                    args: { fileName },
                }),
                type: "default",
                progress: 0,
            });
            return idx;
        });
        if (firstOpen) {
            try {
                this.window.show();
            } catch (error) {
                ztoolkit.log("显示进度窗口失败:", error);
            }
        }
    }

    private static ensureWindow() {
        if (!JobProgressPopup.shared?.window) {
            const window = new ztoolkit.ProgressWindow(
                getString("operation-progress-title"),
                {
                    // 允许点击关闭: 防止异常路径下弹窗永驻且无法交互;
                    // 任务继续时后续更新会重新 show()。
                    closeOnClick: true,
                    closeTime: -1,
                    closeOtherProgressWindows: false,
                },
            );
            JobProgressPopup.shared = {
                window,
                lineCount: 0,
                batches: 0,
                closeToken: 0,
            };
        }
        return JobProgressPopup.shared;
    }

    private createLine(line: { text: string; type: string; progress: number }) {
        if (!this.window || !JobProgressPopup.shared) {
            return;
        }
        this.window.createLine(line);
        JobProgressPopup.shared.lineCount += 1;
        resizeProgressWindow(this.window);
    }

    private changeLine(
        idx: number,
        line: { text: string; type: string; progress: number },
    ) {
        if (!this.window) {
            return;
        }
        try {
            this.window.changeLine({ idx, ...line });
            this.window.show();
            resizeProgressWindow(this.window);
        } catch (error) {
            ztoolkit.log("更新进度窗口失败:", error);
        }
    }

    updateFile(update: JobProgressUpdate) {
        if (!this.enabled) {
            return;
        }
        const idx = this.fileIdx[update.current - 1];
        if (idx === undefined) {
            return;
        }
        const fileProgress = jobProgressPercent({
            ...update,
            current: 1,
            total: 1,
        });
        this.changeLine(idx, {
            text: formatJobProgressText(update),
            type:
                update.phase === "file-failed"
                    ? "error"
                    : update.phase === "file-done"
                      ? "success"
                      : "default",
            progress: fileProgress,
        });
        if (update.phase === "file-done" || update.phase === "file-failed") {
            if (!this.finishedFiles.has(update.current)) {
                this.finishedFiles.add(update.current);
                this.done = Math.min(this.total, this.done + 1);
            }
        }
        const overall = Math.min(
            99,
            Math.round(
                ((this.done +
                    (this.finishedFiles.has(update.current)
                        ? 0
                        : fileProgress / 100)) /
                    this.total) *
                    100,
            ),
        );
        const percentText =
            update.phase === "running" &&
            typeof update.percent === "number" &&
            update.percent > 0
                ? ` · ${Math.round(update.percent)}%`
                : "";
        this.changeLine(this.summaryIdx, {
            text:
                getString("operation-progress-summary", {
                    args: { done: this.done, total: this.total },
                }) + percentText,
            type: "default",
            progress: overall,
        });
    }

    complete(succeeded: number, failed: number) {
        if (!this.enabled) {
            return;
        }
        this.changeLine(this.summaryIdx, {
            text: getString("operation-batch-completed", {
                args: {
                    succeeded,
                    failed,
                    kind:
                        failed > 0 && succeeded === 0
                            ? "failed"
                            : failed > 0
                              ? "mixed"
                              : "success",
                },
            }),
            type:
                failed > 0 && succeeded === 0
                    ? "error"
                    : failed > 0
                      ? "default"
                      : "success",
            progress: 100,
        });
        const shared = JobProgressPopup.shared;
        if (!shared) {
            return;
        }
        shared.batches = Math.max(0, shared.batches - 1);
        if (shared.batches > 0) {
            return;
        }
        const token = ++shared.closeToken;
        Zotero.Promise.delay(8000).then(() => {
            if (
                !JobProgressPopup.shared ||
                JobProgressPopup.shared.closeToken !== token ||
                JobProgressPopup.shared.batches > 0
            ) {
                return;
            }
            try {
                JobProgressPopup.shared.window?.close();
            } catch (error) {
                ztoolkit.log("关闭进度窗口失败:", error);
            }
            JobProgressPopup.shared = null;
        });
    }
}
