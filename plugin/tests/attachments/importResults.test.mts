import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { classifyPDFFileName } from "../../src/attachments/pdfFiles.ts";

function loadImporter(useLocalFiles = false) {
    const attachments: Array<{ fileBaseName: string }> = [];
    const localPaths: string[] = [];
    const context = vm.createContext({
        ztoolkit: { log() {} },
        setTimeout: (callback: () => void) => callback(),
        IOUtils: {
            read: async (path: string) => {
                localPaths.push(path);
                return new Uint8Array([1]);
            },
            remove: async () => {},
        },
        Zotero: {
            Attachments: {
                importFromFile: async (options: any) => {
                    attachments.push(options);
                    return { id: attachments.length };
                },
            },
        },
    });
    const exports: any = {};
    const source = fs.readFileSync(
        new URL("../../src/attachments/importResults.ts", import.meta.url),
        "utf8",
    );
    const js = ts.transpileModule(source, {
        compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022,
        },
    }).outputText;
    const imports: Record<string, any> = {
        "../utils/prefs": {
            getPref: () => false,
            isTrue: (value: unknown) => value === true,
        },
        "../utils/locale": { getString: (key: string) => key },
        "../translation/serverClient": {
            downloadTranslatedFile: async () => {
                if (useLocalFiles) throw new Error("offline");
                return new Uint8Array([1]);
            },
        },
        "../translation/types": { PDFType: { DUAL: "dual" } },
        "./pdfFiles": {
            classifyPDFFileName,
            safeExists: async () => true,
            writeTempPdf: async () => "temporary.pdf",
            safeStorageLeafName: (name: string) => name,
            storageFileBaseName: (name: string) => name.replace(/\.pdf$/i, ""),
        },
        "./titleFormat": { buildAttachmentTitle: () => "translated" },
    };
    vm.runInContext("(function(require, exports) {" + js + "})", context)(
        (name: string) => imports[name] ?? {},
        exports,
    );
    const item = {
        id: 1,
        libraryID: 1,
        isAttachment: () => false,
        getField: () => "",
        getCollections: () => [],
    };
    return {
        handleResponse: exports.handleResponse,
        attachments,
        localPaths,
        item,
    };
}

test("single-output commands omit legacy extra files without shifting their matching local paths", async () => {
    const importer = loadImporter(true);
    for (const output of ["mono", "dual"]) {
        importer.attachments.length = 0;
        importer.localPaths.length = 0;
        await importer.handleResponse(
            {
                status: "success",
                fileList: [
                    "paper-compare.pdf",
                    "paper-mono.pdf",
                    "paper-dual.pdf",
                ],
                filePaths: [
                    "D:/translated/paper-compare.pdf",
                    "D:/translated/paper-mono.pdf",
                    "D:/translated/paper-dual.pdf",
                ],
            },
            importer.item,
            {},
            [output],
        );
        assert.deepEqual(importer.localPaths, [
            `D:/translated/paper-${output}.pdf`,
        ]);
        assert.deepEqual(
            importer.attachments.map(({ fileBaseName }) => fileBaseName),
            [`paper-${output}`],
        );
    }
});

test("operations without an output selection retain the existing attachment behavior", async () => {
    const importer = loadImporter();
    await importer.handleResponse(
        {
            status: "success",
            fileList: ["paper-dual.pdf", "paper-mono.pdf", "paper-compare.pdf"],
        },
        importer.item,
        {},
    );
    assert.deepEqual(
        importer.attachments.map(({ fileBaseName }) => fileBaseName),
        ["paper-dual", "paper-mono", "paper-compare"],
    );
});
