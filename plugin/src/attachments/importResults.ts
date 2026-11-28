import { getPref, isTrue } from "../utils/prefs";
import { getString } from "../utils/locale";
import { downloadTranslatedFile } from "../translation/serverClient";
import {
    PDFType,
    type ServerConfig,
    type PDFOperationOptions,
} from "../translation/types";
import type { TranslationOutput } from "../translation/outputs";
import { buildAttachmentTitle } from "./titleFormat";
import {
    classifyPDFFileName,
    safeExists,
    writeTempPdf,
    safeStorageLeafName,
    storageFileBaseName,
} from "./pdfFiles";

const DOWNLOAD_MAX_RETRIES = 3;
const RETRY_DELAY = 2000;

export async function handleResponse(
    response: any,
    item: Zotero.Item,
    config: ServerConfig,
    outputs?: readonly TranslationOutput[],
) {
    ztoolkit.log("response", response);
    if (response.status === "accepted") {
        throw new Error("任务仍在处理中，尚未完成");
    }
    if (response.status !== "success") {
        ztoolkit.log(`服务器返回错误: ${response.message}`);
        throw new Error(String(response.message || "服务器返回错误"));
    }
    if (!Array.isArray(response.fileList)) {
        ztoolkit.log(`服务器返回的 fileList 不是数组`);
        throw new Error(getString("operation-error-no-files"));
    }
    const fileList = response.fileList as string[];
    const outputDir =
        typeof response.outputDir === "string" ? response.outputDir : "";
    const filePaths = Array.isArray(response.filePaths)
        ? (response.filePaths as string[])
        : [];
    const errors: Error[] = [];
    let attached = 0;
    let requested = 0;
    const attachKeys = new Set<string>();
    for (let i = 0; i < fileList.length; i++) {
        const fileName = fileList[i];
        const fileType = classifyPDFFileName(fileName);
        if (outputs && !outputs.includes(fileType as TranslationOutput)) {
            continue;
        }
        requested++;
        const options = getPDFOptions(fileType);
        try {
            await fetchAndAttachPDF({
                fileName,
                config,
                item,
                options,
                type: fileType,
                localPath: typeof filePaths[i] === "string" ? filePaths[i] : "",
                outputDir,
                attachKeys,
            });
            attached++;
        } catch (error) {
            ztoolkit.log(`处理文件 ${fileName} 时出错:`, error);
            errors.push(
                error instanceof Error ? error : new Error(String(error)),
            );
        }
    }
    if (errors.length > 0) {
        throw new Error(
            getString("operation-error-partial-attachments", {
                args: {
                    attached,
                    total: requested,
                    message: errors.map((error) => error.message).join("; "),
                },
            }),
        );
    }
    if (attached > 0) {
        return;
    }
    throw new Error(getString("operation-error-no-files"));
}

export function getPDFOptions(type: string): PDFOperationOptions {
    return {
        rename: isTrue(getPref("rename")),
        openAfterProcess: isTrue(getPref(`${type}-open`)),
    };
}

export function localPathCandidates(
    fileName: string,
    localPath?: string,
    outputDir?: string,
): string[] {
    const candidates = [localPath || ""];
    if (outputDir) {
        try {
            candidates.push(PathUtils.join(outputDir, fileName));
        } catch (error) {
            ztoolkit.log(
                `拼接本地输出路径失败: ${outputDir} / ${fileName}`,
                error,
            );
        }
    }
    return candidates.filter(
        (path, index, all) => path && all.indexOf(path) === index,
    );
}

export async function attachFromLocalPath(params: {
    localPath: string;
    fileName: string;
    item: Zotero.Item;
    config: ServerConfig;
    options: PDFOperationOptions;
    type: string;
    attachKeys: Set<string>;
}): Promise<boolean> {
    const { localPath, fileName, item, config, options, type, attachKeys } =
        params;
    if (!localPath) {
        return false;
    }
    const exists = await safeExists(localPath);
    if (!exists) {
        return false;
    }
    const service = config.next_service;
    const bytes = await IOUtils.read(localPath);
    const tempPath = await writeTempPdf(bytes);
    try {
        const attached = await addAttachment({
            item,
            filePath: tempPath,
            fileName,
            options,
            type,
            service,
            dualMode: config.dualMode,
            attachKeys,
        });
        if (attached) {
            ztoolkit.log(`已从本地路径添加附件: ${localPath}`);
        }
        return attached;
    } finally {
        try {
            await IOUtils.remove(tempPath);
        } catch (error) {
            ztoolkit.log(`清理临时文件失败: ${tempPath}`, error);
        }
    }
}

export async function fetchAndAttachPDF(params: {
    fileName: string;
    config: ServerConfig;
    item: Zotero.Item;
    options: PDFOperationOptions;
    type: string;
    localPath?: string;
    outputDir?: string;
    retries?: number;
    attachKeys: Set<string>;
}) {
    const { fileName, config, item, options, type } = params;
    const service = config.next_service;
    let httpError: unknown;
    try {
        await retryOperation(
            async () => {
                const bytes = await downloadTranslatedFile(fileName, config);
                const tempPath = await writeTempPdf(bytes);
                try {
                    const attached = await addAttachment({
                        item,
                        filePath: tempPath,
                        fileName,
                        options,
                        type,
                        service,
                        dualMode: config.dualMode,
                        attachKeys: params.attachKeys,
                    });
                    if (!attached) {
                        throw new Error(`未能添加附件: ${fileName}`);
                    }
                    ztoolkit.log(`已通过 HTTP 添加文件: ${fileName}`);
                } finally {
                    try {
                        await IOUtils.remove(tempPath);
                    } catch (error) {
                        ztoolkit.log(`清理临时文件失败: ${tempPath}`, error);
                    }
                }
            },
            params.retries ?? DOWNLOAD_MAX_RETRIES,
            RETRY_DELAY,
        );
        return;
    } catch (error) {
        httpError = error;
        ztoolkit.log(`HTTP 下载附件失败 ${fileName}，尝试本机路径:`, error);
    }

    for (const localPath of localPathCandidates(
        fileName,
        params.localPath,
        params.outputDir,
    )) {
        try {
            const attached = await attachFromLocalPath({
                localPath,
                fileName,
                item,
                config,
                options,
                type,
                attachKeys: params.attachKeys,
            });
            if (attached) {
                return;
            }
        } catch (error) {
            ztoolkit.log(`本地路径导入失败 ${localPath}:`, error);
        }
    }

    throw httpError instanceof Error
        ? httpError
        : new Error(`无法导入文件: ${fileName}`);
}

export async function addAttachment(params: {
    item: Zotero.Item;
    filePath: string; // 文件路径(已经保存到Zotero临时文件夹)
    fileName: string;
    options: PDFOperationOptions; // PDF(rename, open)
    type: string; // PDF处理类型(用于短标题)
    service: string; // 服务(用于短标题)
    dualMode?: string;
    attachKeys: Set<string>;
}): Promise<boolean> {
    const { item, filePath, fileName, options, type, service, attachKeys } =
        params;
    const parentItemID = getParentItemID(item); // 如果本身就是parent条目, 那么会返回id.item
    let targetItem = item;
    if (item.isAttachment() && parentItemID) {
        targetItem = Zotero.Items.get(parentItemID);
    }
    // Server filenames may be valid on Linux/Docker but invalid on the
    // Zotero host (notably Windows). Sanitize using Zotero's own rules
    // before using the name in storage or as the attachment title.
    const leafName = safeStorageLeafName(fileName);
    // 标题格式 (#310): 短标题 / 标题前缀-年份 / 完整标题 / 自定义模板。
    const newTitle = buildAttachmentTitle({
        title: targetItem.getField("title") || "",
        shortTitle: targetItem.getField("shortTitle") || "",
        date: targetItem.getField("date") || "",
        service,
        type,
        dualMode: type === PDFType.DUAL ? params.dualMode : undefined,
        style: getPref("renameStyle")?.toString() || "shortTitle",
        prefixLength: Number(getPref("renamePrefixLength")) || 20,
        template: getPref("renameTemplate")?.toString() || "",
    });
    const attachKey = `${parentItemID ?? "none"}::${service}::${type}::${leafName}`;
    if (attachKeys.has(attachKey)) {
        ztoolkit.log(`跳过本轮重复附件: ${newTitle}`);
        return true;
    }
    // parentItemID and collections cannot both be provided.
    // fileBaseName is the storage leaf without extension; title is only
    // the Zotero item display name. The storage name keeps translated/'s
    // naming format after cross-platform-invalid characters are normalized.
    const attachment = await Zotero.Attachments.importFromFile({
        file: filePath,
        parentItemID: parentItemID == undefined ? undefined : parentItemID,
        libraryID: item.libraryID,
        collections:
            parentItemID == undefined ? getCollections(item) : undefined,
        fileBaseName: storageFileBaseName(leafName),
        title: options.rename ? newTitle : leafName,
    });
    if (!attachment?.id) {
        ztoolkit.log(`importFromFile 未返回附件: ${newTitle}`);
        return false;
    }
    attachKeys.add(attachKey);
    if (options.openAfterProcess) {
        try {
            Zotero.Reader.open(attachment.id);
        } catch (error) {
            ztoolkit.log(`附件已添加，但打开阅读器失败: ${newTitle}`, error);
        }
    }
    return true;
}

export async function retryOperation<T>(
    operation: () => Promise<T>,
    maxRetries: number = DOWNLOAD_MAX_RETRIES,
    delay: number = RETRY_DELAY,
): Promise<T> {
    let lastError: Error;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            return await operation();
        } catch (error) {
            lastError =
                error instanceof Error ? error : new Error(String(error));
            if (attempt === maxRetries) {
                throw lastError;
            }
            ztoolkit.log(
                `操作失败，第 ${attempt} 次重试 (共 ${maxRetries} 次): ${lastError.message}`,
            );
            await new Promise((resolve) =>
                setTimeout(resolve, delay * attempt),
            );
        }
    }
    throw lastError!;
}

export function getParentItemID(item: Zotero.Item): number | undefined {
    let ID;
    if (item.isAttachment()) {
        const parentItemID = item.parentItemID;
        ID =
            parentItemID != null && parentItemID !== false
                ? parentItemID
                : undefined;
    } else {
        ID = item.id;
    }
    return ID;
}

export function getCollections(item: Zotero.Item): number[] | undefined {
    const collections = item.getCollections();
    return collections.length > 0 ? [collections[0]] : undefined;
}
