import { getString } from "../utils/locale";
import { getTranslationConfig } from "../settings/translationConfig";
import {
    reloadApiConfigurations,
    getActiveApiConfiguration,
} from "../settings/apiConfigurations";
import {
    classifyPDFFileName,
    validatePDFAttachment,
    prepareFileData,
} from "../attachments/pdfFiles";
import { handleResponse } from "../attachments/importResults";
import { sendRequest } from "./serverClient";
import { JobProgressPopup, showTranslationNotice } from "./progress";
import {
    translationOutputsForMode,
    translationOutputSettings,
    type TranslationMode,
    type TranslationOutput,
} from "./outputs";
import { PDFType, type JobProgressUpdate, type TranslationTask } from "./types";

export async function processSelectedDocuments(
    endpoint: string, // 仅包含请求类型
    mode?: TranslationMode,
) {
    const pane = ztoolkit.getGlobal("ZoteroPane");
    const selectedItems = pane.getSelectedItems();
    if (selectedItems.length == 0) {
        ztoolkit.getGlobal("alert")(getString("operation-error-no-selection"));
        return;
    }
    const tasks: TranslationTask[] = [];
    for (const item of selectedItems) {
        try {
            const filepath = await validatePDFAttachment(item);
            const fileName = PathUtils.filename(filepath);
            const inputType = classifyPDFFileName(fileName);
            const operationError = getOperationValidationError(
                endpoint,
                inputType,
            );
            if (operationError) {
                throw new Error(operationError);
            }
            const config = getTranslationConfig();
            if (mode) {
                Object.assign(config, translationOutputSettings(mode));
            }
            const outputs: readonly TranslationOutput[] | undefined = mode
                ? translationOutputsForMode(mode)
                : undefined;
            tasks.push({
                fileName,
                item,
                config,
                endpoint,
                outputs,
            });
        } catch (error) {
            const message =
                error instanceof Error
                    ? error.message
                    : getString("operation-error-unknown");
            ztoolkit.getGlobal("alert")(
                getString("operation-error-prefix", {
                    args: { message },
                }),
            );
        }
    }
    if (tasks.length === 0) {
        return;
    }

    const progress = JobProgressPopup.open(tasks.map((task) => task.fileName));
    try {
        const result = await processBatch(tasks, (update) => {
            progress.updateFile(update);
        });
        progress.complete(result.succeeded, result.failed);
    } catch (error) {
        progress.complete(0, tasks.length);
        throw error;
    }
}

export async function processBatch(
    tasks: TranslationTask[],
    onProgress?: (update: JobProgressUpdate) => void,
): Promise<{ total: number; succeeded: number; failed: number }> {
    let succeeded = 0;
    let failed = 0;
    for (let index = 0; index < tasks.length; index++) {
        const report = (
            update: Omit<JobProgressUpdate, "current" | "total">,
        ) => {
            onProgress?.({
                ...update,
                current: index + 1,
                total: tasks.length,
            });
        };
        try {
            await processSingleFile(tasks[index], report);
            succeeded++;
        } catch {
            failed++;
        }
    }
    return { total: tasks.length, succeeded, failed };
}

export function getOperationValidationError(
    endpoint: string,
    inputType: string,
): string | null {
    const allowed: Record<string, string[]> = {
        translate: [PDFType.ORIGIN],
        crop: [PDFType.ORIGIN, PDFType.MONO, PDFType.DUAL],
        compare: [PDFType.ORIGIN, PDFType.DUAL],
        "crop-compare": [PDFType.ORIGIN, PDFType.DUAL, PDFType.DUAL_CUT],
    };

    if (endpoint === "crop-compare" && inputType === PDFType.CROP_COMPARE) {
        return getString("operation-error-crop-compare-terminal");
    }
    if (endpoint === "compare" && inputType === PDFType.COMPARE) {
        return getString("operation-error-compare-terminal");
    }
    const accepted = allowed[endpoint];
    if (!accepted || accepted.includes(inputType)) {
        return null;
    }
    const key =
        endpoint === "translate"
            ? "operation-error-translate"
            : endpoint === "crop"
              ? "operation-error-crop"
              : endpoint === "compare"
                ? "operation-error-compare"
                : "operation-error-crop-compare";
    return getString(key);
}

export async function processSingleFile(
    params: TranslationTask,
    onProgress?: (update: Omit<JobProgressUpdate, "current" | "total">) => void,
) {
    const { fileName, item, config, endpoint } = params; // config
    ztoolkit.log(
        `Processing Single File: ${fileName}, ServerConfig: ${config}`,
    );
    try {
        onProgress?.({ phase: "submitting", fileName, endpoint });
        const fileData = await prepareFileData(item);
        reloadApiConfigurations();
        const activeApi = getActiveApiConfiguration(config.next_service);
        const apiConfiguration = activeApi
            ? {
                  service: activeApi.service,
                  model: activeApi.model,
                  apiKey: activeApi.apiKey,
                  apiUrl: activeApi.apiUrl,
                  extraData: activeApi.extraData || {},
              }
            : undefined;
        const response = await sendRequest(
            fileData,
            config,
            endpoint,
            apiConfiguration,
            onProgress,
            showTranslationNotice,
        );
        onProgress?.({ phase: "importing", fileName, endpoint });
        await handleResponse(response, item, config, params.outputs);
        onProgress?.({ phase: "file-done", fileName, endpoint });
    } catch (error) {
        ztoolkit.log(`处理单个文件失败: ${fileName}, 错误: ${error}`);
        const message =
            error instanceof Error
                ? error.message
                : getString("operation-error-unknown");
        onProgress?.({
            phase: "file-failed",
            fileName,
            endpoint,
            error: message,
        });
        // alert 是模态框: 超长引擎输出会把对话框撑满屏幕且难以关闭。
        const alertMessage =
            message.length > 300
                ? `${message.slice(0, 300)}\n…(已截断，完整错误请查看 server 终端日志)`
                : message;
        ztoolkit.getGlobal("alert")(
            getString("operation-error-single-file", {
                args: { fileName, message: alertMessage },
            }),
        );
        // The batch counts this failure after the per-file message is shown.
        throw error;
    }
}
