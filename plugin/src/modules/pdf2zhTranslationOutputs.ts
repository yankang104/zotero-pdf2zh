import type { ServerConfig } from "./pdf2zhTypes";

export type TranslationOutput = "compare" | "dual" | "mono";
export type TranslationMode = "mono" | "dual-lr" | "dual-tb";

export type TranslationOutputSettings = Pick<
    ServerConfig,
    | "mono"
    | "dual"
    | "mono_cut"
    | "dual_cut"
    | "crop_compare"
    | "compare"
    | "noDual"
    | "noMono"
> &
    Partial<Pick<ServerConfig, "dualMode">>;

/** Map one translation command to its per-task export and layout flags. */
export function translationOutputSettings(
    mode: TranslationMode,
): TranslationOutputSettings {
    const mono = mode === "mono";

    return {
        mono: String(mono),
        dual: String(!mono),
        mono_cut: "false",
        dual_cut: "false",
        crop_compare: "false",
        compare: "false",
        noMono: String(!mono),
        noDual: String(mono),
        ...(!mono ? { dualMode: mode === "dual-lr" ? "LR" : "TB" } : {}),
    };
}

/** Match layouts actually exposed by each Server engine command. */
export function supportsTranslationMode(
    mode: TranslationMode,
    config: Pick<ServerConfig, "engine" | "babeldoc">,
): boolean {
    if (config.engine === "pdf2zh_next") return true;
    if (config.engine === "wenyi") return mode !== "dual-tb";
    if (config.engine !== "pdf2zh") return false;
    if (mode === "mono") return true;
    const babeldoc = config.babeldoc === "true" || config.babeldoc === "True";
    return mode === (babeldoc ? "dual-lr" : "dual-tb");
}
