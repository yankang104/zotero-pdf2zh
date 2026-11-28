import { getPref } from "../utils/prefs";
import { tableModeFromPref } from "../translation/capabilities";
import type { ServerConfig } from "../translation/types";

export function getTranslationConfig(): ServerConfig {
    const config: ServerConfig = {
        serverUrl: getPref("new_serverip")?.toString() || "",

        engine: "pdf2zh_next",
        next_service: getPref("next_service")?.toString() || "",

        sourceLang: getPref("sourceLang")?.toString() || "",
        targetLang: getPref("targetLang")?.toString() || "",

        skipLastPages: getPref("skipLastPages")?.toString() || "",
        qps: getPref("qps")?.toString() || "10",
        poolSize: getPref("poolSize")?.toString() || "0",

        // generate
        mono: getPref("mono")?.toString() || "",
        dual: getPref("dual")?.toString() || "",
        mono_cut: getPref("mono-cut")?.toString() || "",
        dual_cut: getPref("dual-cut")?.toString() || "",
        crop_compare: getPref("crop-compare")?.toString() || "",
        compare: getPref("compare")?.toString() || "",

        // TODO: 如果noDual和noMono同时被选择, 我们默认不选择noDual
        fontFamily: getPref("fontFamily")?.toString() || "",
        dualMode: getPref("dualMode")?.toString() || "",
        transFirst: getPref("transFirst")?.toString() || "",
        ocr: getPref("ocr")?.toString() || "",
        autoOcr: getPref("autoOcr")?.toString() || "",
        noWatermark: getPref("noWatermark")?.toString() || "",
        saveGlossary: getPref("saveGlossary")?.toString() || "",
        disableGlossary: getPref("disableGlossary")?.toString() || "",
        noDual: getPref("noDual")?.toString() || "",
        noMono: getPref("noMono")?.toString() || "",
        skipClean: getPref("skipClean")?.toString() || "",
        disableRichTextTranslate:
            getPref("disableRichTextTranslate")?.toString() || "",
        enhanceCompatibility: getPref("enhanceCompatibility")?.toString() || "",
        translateTableText: getPref("translateTableText")?.toString() || "",
        skipReferences: getPref("skipReferences") === true ? "true" : "",
        tableMode: tableModeFromPref(
            getPref("prettierTables"),
            getPref("translateTableText"),
        ),
        ignoreCache: getPref("ignoreCache") === true ? "true" : "",
        onlyIncludeTranslatedPage:
            getPref("onlyIncludeTranslatedPage")?.toString() || "",
    };
    return config;
}
