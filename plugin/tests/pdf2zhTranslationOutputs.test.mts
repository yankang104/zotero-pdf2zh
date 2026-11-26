import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { classifyPDFFileName } from "../src/modules/pdf2zhAttachmentUtils.ts";
import {
    supportsTranslationMode,
    translationOutputSettings,
    type TranslationMode,
} from "../src/modules/pdf2zhTranslationOutputs.ts";

test("mono exports only the translated edition without overriding its unused dual layout", () => {
    assert.deepEqual(translationOutputSettings("mono"), {
        mono: "true",
        dual: "false",
        mono_cut: "false",
        dual_cut: "false",
        crop_compare: "false",
        compare: "false",
        noMono: "false",
        noDual: "true",
    });
});

test("each bilingual command exports dual in its requested layout without comparison files", () => {
    for (const [mode, dualMode] of [
        ["dual-lr", "LR"],
        ["dual-tb", "TB"],
    ] as const) {
        assert.deepEqual(translationOutputSettings(mode), {
            mono: "false",
            dual: "true",
            mono_cut: "false",
            dual_cut: "false",
            crop_compare: "false",
            compare: "false",
            noMono: "true",
            noDual: "false",
            dualMode,
        });
    }
});

test("available commands match the layout flags actually exposed by each engine", () => {
    const modes: TranslationMode[] = ["mono", "dual-lr", "dual-tb"];
    const engines = [
        {
            engine: "pdf2zh_next",
            babeldoc: "false",
            expected: [true, true, true],
        },
        { engine: "wenyi", babeldoc: "false", expected: [true, true, false] },
        { engine: "pdf2zh", babeldoc: "false", expected: [true, false, true] },
        { engine: "pdf2zh", babeldoc: "true", expected: [true, true, false] },
        { engine: "pdf2zh", babeldoc: "True", expected: [true, true, false] },
        {
            engine: "unavailable",
            babeldoc: "false",
            expected: [false, false, false],
        },
    ];
    for (const config of engines) {
        assert.deepEqual(
            modes.map((mode) => supportsTranslationMode(mode, config)),
            config.expected,
            `${config.engine}, babeldoc=${config.babeldoc}`,
        );
    }
});

function loadHelper() {
    const context = vm.createContext({ ztoolkit: { log() {} } });
    const exports: any = {};
    const source = fs.readFileSync(
        new URL("../src/modules/pdf2zhHelper.ts", import.meta.url),
        "utf8",
    );
    const js = ts.transpileModule(source, {
        compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022,
        },
    }).outputText;
    const imports: Record<string, any> = {
        "../../package.json": { version: "test" },
        "../utils/prefs": { getPref: () => false },
        "../utils/locale": { getString: (key: string) => key },
        "./pdf2zhAttachmentUtils": { classifyPDFFileName },
    };
    vm.runInContext(`(function(require, exports) {${js}})`, context)(
        (name: string) => imports[name] ?? {},
        exports,
    );
    return exports.PDF2zhHelperFactory;
}

test("single-output commands omit legacy extra files without shifting their matching local paths", async () => {
    const helper = loadHelper();
    const attachments: Array<{
        fileName: string;
        type: string;
        localPath: string;
    }> = [];
    helper.fetchAndAttachPDF = async (params: any) => attachments.push(params);
    for (const output of ["mono", "dual"]) {
        attachments.length = 0;
        await helper.handleResponse(
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
            {},
            {},
            [output],
        );
        assert.deepEqual(
            attachments.map(({ fileName, type, localPath }) => ({
                fileName,
                type,
                localPath,
            })),
            [
                {
                    fileName: `paper-${output}.pdf`,
                    type: output,
                    localPath: `D:/translated/paper-${output}.pdf`,
                },
            ],
        );
    }
});

test("operations without an output selection retain the existing attachment behavior", async () => {
    const helper = loadHelper();
    const attachments: string[] = [];
    helper.fetchAndAttachPDF = async (params: any) =>
        attachments.push(params.fileName);
    await helper.handleResponse(
        {
            status: "success",
            fileList: ["paper-dual.pdf", "paper-mono.pdf", "paper-compare.pdf"],
        },
        {},
        {},
    );
    assert.deepEqual(attachments, [
        "paper-dual.pdf",
        "paper-mono.pdf",
        "paper-compare.pdf",
    ]);
});
