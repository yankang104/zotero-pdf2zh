export enum PDFType {
    MONO = "mono",
    DUAL = "dual",
    MONO_CUT = "mono-cut",
    DUAL_CUT = "dual-cut",
    CROP_COMPARE = "crop-compare",
    COMPARE = "compare",
    ORIGIN_CUT = "origin-cut",
    ORIGIN = "origin",
    UNKNOWN = "unknown",
}

export interface ServerConfig {
    serverUrl: string;
    qps: string;
    poolSize: string;
    engine: string;
    next_service: string;

    skipLastPages: string;
    sourceLang: string;
    targetLang: string;
    // generate
    mono: string;
    mono_cut: string;
    dual: string;
    dual_cut: string;
    crop_compare: string;
    compare: string;

    ocr: string;
    autoOcr: string;
    transFirst: string;
    noWatermark: string;
    fontFamily: string;
    dualMode: string;
    saveGlossary: string;
    disableGlossary: string;
    noDual: string;
    noMono: string;
    skipClean: string;
    disableRichTextTranslate: string;
    enhanceCompatibility: string;
    translateTableText: string;
    skipReferences: string;
    tableMode?: import("./capabilities").TableMode | "";
    ignoreCache: string;
    onlyIncludeTranslatedPage: string;
}

export interface PDFOperationOptions {
    rename: boolean;
    openAfterProcess: boolean;
}

export type JobProgressPhase =
    | "submitting"
    | "accepted"
    | "running"
    | "importing"
    | "file-done"
    | "file-failed";

export interface JobProgressUpdate {
    phase: JobProgressPhase;
    fileName: string;
    endpoint: string;
    current: number;
    total: number;
    percent?: number;
    detail?: string;
    error?: string;
}

export interface TranslationTask {
    fileName: string;
    item: Zotero.Item;
    config: ServerConfig;
    endpoint: string;
    outputs?: readonly import("./outputs").TranslationOutput[];
}

export interface TranslationNotice {
    key: string;
    message: string | null;
    type?: "default" | "fail";
}
