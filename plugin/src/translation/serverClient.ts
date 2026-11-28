import { version as pluginVersion } from "../../package.json";
import { getString } from "../utils/locale";
import { presentableError } from "../errorCatalog";
import type { LLMApiData } from "../settings/apiConfigurations";
import { validatePDFBytes } from "../attachments/pdfFiles";
import {
    supportsTableMode,
    supportsReferenceSkip,
    needsDeepSeekFlashPatch,
    supportsDeepSeekFlashPatch,
    needsRelayPatch,
    supportsRelayPatch,
} from "./capabilities";
import type {
    ServerConfig,
    JobProgressUpdate,
    TranslationNotice,
} from "./types";

const COMPLETED_FILE_GRACE_MS = 20_000;

export async function sendRequest(
    fileData: { fileName: string; base64: string },
    config: ServerConfig,
    endpoint: string,
    llmApiConfig: Partial<LLMApiData> | undefined,
    onProgress?: (update: Omit<JobProgressUpdate, "current" | "total">) => void,
    onNotice?: (notice: TranslationNotice) => void,
) {
    const requestBody: any = {
        fileName: fileData.fileName,
        fileContent: fileData.base64,
        ...config, // 发送config数据
        // 新协议：Server 立刻返回 accepted + taskId，插件再轮询。
        // 没带这个标记的旧插件（含 DCC 4.0.3）会走 Server 同步返回 fileList。
        asyncJob: true,
    };
    const wantsTableMode = Boolean(config.tableMode);
    const wantsReferenceSkip = config.skipReferences === "true";
    const wantsFlashPatch = needsDeepSeekFlashPatch(llmApiConfig);
    const wantsRelayPatch = needsRelayPatch(llmApiConfig);
    if (
        wantsTableMode ||
        wantsReferenceSkip ||
        wantsFlashPatch ||
        wantsRelayPatch
    ) {
        const serverUrl = normalizeServerUrl(config.serverUrl);
        const health = await fetch(serverUrl + "/health", {
            cache: "no-store",
        });
        if (!health.ok) {
            throw new Error(
                "Server capability check failed: HTTP " + health.status,
            );
        }
        const capabilities: unknown = await health.json();
        if (wantsRelayPatch && !supportsRelayPatch(capabilities)) {
            throw new Error(getString("operation-error-relay-server"));
        }
        if (wantsFlashPatch && !supportsDeepSeekFlashPatch(capabilities)) {
            throw new Error(
                "当前 Server 不支持 deepseek-flash 安全关闭思考。为避免产生额外思考费用，本次未发送翻译请求。请先更新 Server 后再试。",
            );
        }
        if (wantsTableMode && config.tableMode) {
            const supported = supportsTableMode(config.tableMode, capabilities);
            if (!supported) delete requestBody.tableMode;
            onNotice?.({
                key: "table:" + serverUrl,
                message: supported
                    ? null
                    : getString("operation-table-native-fallback"),
            });
        } else {
            delete requestBody.tableMode;
        }
        if (wantsReferenceSkip) {
            const supported = supportsReferenceSkip(capabilities);
            if (!supported) delete requestBody.skipReferences;
            onNotice?.({
                key: "reference:" + serverUrl,
                message: supported
                    ? null
                    : getString("operation-reference-native-fallback"),
            });
        } else {
            delete requestBody.skipReferences;
        }
    } else {
        delete requestBody.tableMode;
        delete requestBody.skipReferences;
    }
    ztoolkit.log("server config: ", config);
    // 如果有激活的 LLM API 配置，添加到请求中
    if (llmApiConfig) {
        requestBody.llm_api = llmApiConfig;
        ztoolkit.log("llmApiConfig", {
            service: llmApiConfig.service,
            model: llmApiConfig.model,
            apiUrl: llmApiConfig.apiUrl,
            apiKey: llmApiConfig.apiKey ? "********" : "",
            extraDataKeys: Object.keys(llmApiConfig.extraData || {}),
        });
    }
    const response = await fetch(`${config.serverUrl}/${endpoint}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-PDF2zh-Protocol": "accepted",
            "X-PDF2zh-Plugin-Version": pluginVersion,
        },
        body: JSON.stringify(requestBody),
        cache: "no-store",
    });
    const text = await response.text();
    let result: {
        status?: string;
        message?: string;
        taskId?: string;
        [key: string]: unknown;
    };
    try {
        result = parseServerPayload(text);
    } catch (error) {
        ztoolkit.log(`response`, response, text);
        throw new Error(
            text ||
                (error instanceof Error
                    ? error.message
                    : `服务器返回错误 HTTP ${response.status}`),
        );
    }
    if (
        !response.ok ||
        result.status === "error" ||
        result.status === "failed"
    ) {
        ztoolkit.log(`response`, response, result);
        throw new Error(presentableError(result.message || "服务器返回错误"));
    }
    notifyServerWarnings(result, config, onNotice);
    const taskId = taskIdFromPayload(result);
    if (
        result.status === "accepted" ||
        (taskId && result.status !== "success")
    ) {
        if (!taskId) {
            throw new Error("服务器已接收任务，但没有返回 taskId");
        }
        onProgress?.({
            phase: "accepted",
            fileName: fileData.fileName,
            endpoint,
        });
        return waitForAcceptedTask(config, taskId, (running) => {
            onProgress?.({
                phase: "running",
                fileName: fileData.fileName,
                endpoint,
                percent: running.percent,
                detail: running.message,
            });
        });
    }
    return result;
}

function notifyServerWarnings(
    payload: Record<string, unknown>,
    config: ServerConfig,
    onNotice?: (notice: TranslationNotice) => void,
): void {
    const serverUrl = normalizeServerUrl(config.serverUrl);
    for (const warning of stringList(payload.warnings)) {
        onNotice?.({
            key: "server:" + serverUrl + "|" + warning,
            message: warning,
            type: "fail",
        });
    }
}

function stringList(value: unknown): string[] {
    return Array.isArray(value)
        ? value.filter(
              (item): item is string =>
                  typeof item === "string" && item.length > 0,
          )
        : [];
}

export function taskFinishedWithoutFiles(
    task: Record<string, unknown> | undefined,
    taskId: string,
): boolean {
    if (!task || taskIdFromPayload(task) !== taskId) {
        return false;
    }
    const nested =
        task.result && typeof task.result === "object"
            ? (task.result as Record<string, unknown>)
            : null;
    const status = String(task.status || nested?.status || "");
    const completed =
        task.finished === true ||
        status === "完成" ||
        status === "success" ||
        nested?.status === "success";
    const failed =
        status === "失败" || status === "failed" || nested?.status === "error";
    const files = stringList(nested?.fileList ?? task.fileList);
    const paths = stringList(nested?.filePaths ?? task.filePaths);
    return completed && !failed && files.length === 0 && paths.length === 0;
}

export function parseServerPayload(text: string): {
    status?: string;
    message?: string;
    taskId?: string;
    task_id?: string;
    [key: string]: unknown;
} {
    const trimmed = (text || "").trim();
    if (!trimmed) {
        throw new Error("服务器返回为空");
    }
    return JSON.parse(trimmed) as {
        status?: string;
        message?: string;
        taskId?: string;
        task_id?: string;
        [key: string]: unknown;
    };
}

export function taskIdFromPayload(payload: {
    taskId?: unknown;
    task_id?: unknown;
}): string {
    const raw = payload.taskId ?? payload.task_id ?? "";
    return typeof raw === "string" || typeof raw === "number"
        ? String(raw).trim()
        : "";
}

export function completedTaskPayload(
    task: Record<string, unknown> | undefined,
    taskId: string,
): { status: string; message?: string; [key: string]: unknown } | null {
    if (!task || Array.isArray(task.tasks) || Array.isArray(task.history)) {
        return null;
    }
    const id = taskIdFromPayload(task);
    if (!id || id !== taskId) {
        return null;
    }
    const nested =
        task.result && typeof task.result === "object"
            ? (task.result as Record<string, unknown>)
            : null;
    const status = String(task.status || nested?.status || "");
    const failed =
        status === "失败" ||
        status === "failed" ||
        nested?.status === "error" ||
        (task.finished === true && status !== "完成" && status !== "success");
    if (failed) {
        return {
            status: "error",
            message: presentableError(
                String(
                    nested?.message || task.error || task.message || "翻译失败",
                ),
            ),
        };
    }
    const files = stringList(nested?.fileList ?? task.fileList);
    const paths = stringList(nested?.filePaths ?? task.filePaths);
    const succeeded =
        (task.finished === true ||
            status === "完成" ||
            status === "success" ||
            nested?.status === "success") &&
        (files.length > 0 || paths.length > 0);
    if (!succeeded) {
        return null;
    }
    if (nested && nested.status === "success" && files.length > 0) {
        return nested as { status: string; message?: string };
    }
    return {
        status: "success",
        fileList: files,
        filePaths: paths,
        outputDir: String(nested?.outputDir || task.outputDir || ""),
    };
}

export async function fetchTaskRecord(
    config: ServerConfig,
    taskId: string,
): Promise<Record<string, unknown> | undefined> {
    const base = normalizeServerUrl(config.serverUrl);
    try {
        const tasksRes = await fetch(`${base}/api/tasks`, {
            cache: "no-store",
        });
        const tasksData = tasksRes.ok
            ? ((await tasksRes.json()) as {
                  tasks?: Array<Record<string, unknown>>;
              })
            : { tasks: [] };
        const tasks = Array.isArray(tasksData.tasks) ? tasksData.tasks : [];
        const matched = tasks.find(
            (task) => taskIdFromPayload(task) === taskId,
        );
        if (matched) {
            return matched;
        }
        const historyRes = await fetch(`${base}/api/history`, {
            cache: "no-store",
        });
        const historyData = historyRes.ok
            ? ((await historyRes.json()) as {
                  history?: Array<Record<string, unknown>>;
              })
            : { history: [] };
        const history = Array.isArray(historyData.history)
            ? historyData.history
            : [];
        return history.find((task) => taskIdFromPayload(task) === taskId);
    } catch (error) {
        ztoolkit.log("读取翻译任务状态失败:", error);
        return undefined;
    }
}

export async function fetchCompletedTask(
    config: ServerConfig,
    taskId: string,
): Promise<{
    status: string;
    message?: string;
    [key: string]: unknown;
} | null> {
    const task = await fetchTaskRecord(config, taskId);
    return completedTaskPayload(task, taskId);
}

export async function waitForAcceptedTask(
    config: ServerConfig,
    taskId: string,
    onRunning?: (info: { percent: number; message: string }) => void,
): Promise<{ status: string; message?: string; [key: string]: unknown }> {
    // Zotero 插件沙箱没有 AbortController / ReadableStream / EventSource，
    // 不能去拉无限的 /events。POST 已经成功开工，这里只等这个 taskId 结束。
    const deadline = Date.now() + 3 * 60 * 60 * 1000;
    let completedWithoutFilesSince: number | null = null;
    while (Date.now() < deadline) {
        const task = await fetchTaskRecord(config, taskId);
        const payload = completedTaskPayload(task, taskId);
        if (payload) {
            if (payload.status === "error") {
                throw new Error(
                    presentableError(payload.message || "翻译失败"),
                );
            }
            const files = stringList(payload.fileList);
            ztoolkit.log(
                `任务 ${taskId} 已完成，准备导入 ${files.length} 个文件`,
            );
            return payload;
        }
        if (taskFinishedWithoutFiles(task, taskId)) {
            completedWithoutFilesSince ??= Date.now();
            if (
                Date.now() - completedWithoutFilesSince >=
                COMPLETED_FILE_GRACE_MS
            ) {
                throw new Error(
                    getString("operation-error-completed-no-files"),
                );
            }
            ztoolkit.log(
                `任务 ${taskId} 标记完成但还没有文件，等待 Server 落盘`,
            );
        } else {
            completedWithoutFilesSince = null;
        }
        if (task && task.finished !== true) {
            const raw = Number(task.progress);
            onRunning?.({
                percent: Number.isFinite(raw) ? raw : 0,
                message: String(task.message || task.status || ""),
            });
        }
        await Zotero.Promise.delay(1000);
    }
    throw new Error("等待翻译结果超时");
}

export function normalizeServerUrl(serverUrl: string): string {
    return (serverUrl || "").trim().replace(/\/+$/, "");
}

export function translatedFileUrl(serverUrl: string, fileName: string): string {
    return `${normalizeServerUrl(serverUrl)}/translatedFile/${encodeURIComponent(fileName)}`;
}

export async function downloadTranslatedFile(
    fileName: string,
    config: ServerConfig,
): Promise<Uint8Array> {
    const url = translatedFileUrl(config.serverUrl, fileName);
    const response = await fetch(url, { method: "GET" });
    if (!response.ok) {
        throw new Error(`下载失败 HTTP ${response.status}: ${fileName}`);
    }
    const buffer = await response.arrayBuffer();
    if (!buffer || buffer.byteLength === 0) {
        throw new Error(`下载文件为空: ${fileName}`);
    }
    const bytes = new Uint8Array(buffer);
    validatePDFBytes(bytes, fileName);
    return bytes;
}
