export function isPDFPath(path: string | null | undefined): boolean {
    return typeof path === "string" && /\.pdf$/i.test(path);
}

const PRODUCT_SUFFIXES: [suffix: string, type: string][] = [
    // Order matters: longer markers first (mono-cut also ends with -cut).
    ["-mono-cut.pdf", "mono-cut"],
    [".mono-cut.pdf", "mono-cut"],
    ["-dual-cut.pdf", "dual-cut"],
    [".dual-cut.pdf", "dual-cut"],
    ["-crop-compare.pdf", "crop-compare"],
    [".crop-compare.pdf", "crop-compare"],
    ["-compare.pdf", "compare"],
    [".compare.pdf", "compare"],
    ["-cut.pdf", "origin-cut"],
    [".cut.pdf", "origin-cut"],
    ["-mono.pdf", "mono"],
    [".mono.pdf", "mono"],
    ["-dual.pdf", "dual"],
    [".dual.pdf", "dual"],
    [".lr_dual.pdf", "dual"],
    [".tb_dual.pdf", "dual"],
];

/**
 * Classify a PDF as one of our translated products by its filename.
 * Only names ENDING in a product marker ("-mono.pdf" for the legacy
 * engine, ".zh-CN.dual.pdf" style for pdf2zh_next) count; a paper
 * whose title merely ends in "dual.pdf" is the user's own file and
 * must stay translatable.
 */
export function classifyPDFFileName(fileName: string): string {
    const name = String(fileName || "").toLowerCase();
    for (const [suffix, type] of PRODUCT_SUFFIXES) {
        if (name.endsWith(suffix)) {
            return type;
        }
    }
    return "origin";
}

function containsBytes(
    bytes: Uint8Array,
    needle: readonly number[],
    start: number,
    end: number,
): boolean {
    const first = Math.max(0, start);
    const last = Math.min(bytes.length, end) - needle.length;
    for (let i = first; i <= last; i++) {
        let matched = true;
        for (let j = 0; j < needle.length; j++) {
            if (bytes[i + j] !== needle[j]) {
                matched = false;
                break;
            }
        }
        if (matched) {
            return true;
        }
    }
    return false;
}

export function validatePDFBytes(bytes: Uint8Array, fileName: string): void {
    // Be lenient about harmless leading/trailing bytes, but reject common
    // HTTP 200 error pages and truncated downloads before Zotero imports them.
    const hasHeader = containsBytes(
        bytes,
        [0x25, 0x50, 0x44, 0x46, 0x2d], // %PDF-
        0,
        Math.min(bytes.length, 1024),
    );
    const hasEOF = containsBytes(
        bytes,
        [0x25, 0x25, 0x45, 0x4f, 0x46], // %%EOF
        Math.max(0, bytes.length - 65_536),
        bytes.length,
    );
    if (!hasHeader || !hasEOF) {
        throw new Error(`下载内容不是完整 PDF: ${fileName}`);
    }
}

export async function prepareFileData(
    item: Zotero.Item,
): Promise<{ fileName: string; base64: string }> {
    const filepath = await validatePDFAttachment(item);
    const fileName = PathUtils.filename(filepath);
    const base64 = await readPDFAsBase64(filepath);
    return { fileName, base64 }; // 返回PDF数据用于传输, 返回fileName
}

export async function blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

export async function safeExists(path: string) {
    try {
        return await IOUtils.exists(path);
    } catch (error) {
        ztoolkit.log(`检查路径 ${path} 时出错:`, error);
        return false;
    }
}

export async function getAttachmentItem(
    item: Zotero.Item,
): Promise<Zotero.Item | false> {
    let attachItem;
    if (item.isAttachment()) {
        attachItem = item;
    } else if (item.isRegularItem()) {
        const bestItem = await item.getBestAttachment(); // 最早添加的附件Item
        attachItem = bestItem;
    }
    if (!attachItem) return false;
    return attachItem;
}

export async function validatePDFAttachment(
    item: Zotero.Item,
): Promise<string> {
    const attachItem = await getAttachmentItem(item); // 获取item对应的attchItem
    if (!attachItem) return "No valid attachment found";
    const filepath = attachItem.getFilePath().toString();
    if (!isPDFPath(filepath)) throw new Error("Please select a PDF attachment");
    const exists = await safeExists(filepath);
    if (!exists) throw new Error("PDF file not found");
    return filepath;
}

export async function readPDFAsBase64(filepath: string): Promise<string> {
    const contentRaw = await IOUtils.read(filepath);
    const blob = new Blob([contentRaw], { type: "application/pdf" });
    return blobToBase64(blob);
}

export function storageLeafName(fileName: string): string {
    const leaf = String(fileName || "")
        .replace(/^.*[/\\]/, "")
        .trim();
    return leaf || "translated.pdf";
}

export function storageFileBaseName(fileName: string): string {
    const leaf = storageLeafName(fileName);
    return leaf.replace(/\.pdf$/i, "") || leaf;
}

export function safeStorageLeafName(fileName: string): string {
    const leaf = storageLeafName(fileName);
    // Preserve the translated filename structure and semantic suffixes;
    // only cross-platform-invalid characters are normalized by Zotero.
    return Zotero.File.getValidFileName(leaf) || "translated.pdf";
}

export async function writeTempPdf(bytes: Uint8Array): Promise<string> {
    // Keep the temp leaf ASCII-only. PathUtils.join/filename reject some
    // Docker paths and unicode names (e.g. "Shi 等 - test.pdf") with
    // NS_ERROR_FILE_UNRECOGNIZED_PATH on Windows. importFromFile later
    // copies this file into storage/ using fileBaseName, so the temp
    // name is only a transfer vehicle.
    const tempName = `pdf2zh-${Date.now()}-${Math.random()
        .toString(36)
        .slice(2, 10)}.pdf`;
    const tempPath = PathUtils.join(PathUtils.tempDir, tempName);
    await IOUtils.write(tempPath, bytes);
    return tempPath;
}
