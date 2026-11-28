import type { ServerConfig } from "./types";

export type TranslationOutput = "compare" | "dual" | "mono";
export type TranslationMode = "both" | "mono" | "dual-lr" | "dual-tb";

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

/** Select the PDF editions imported for one translation menu command. */
export function translationOutputsForMode(
    mode: TranslationMode,
): readonly TranslationOutput[] {
    if (mode === "both") return ["mono", "dual"];
    return [mode === "mono" ? "mono" : "dual"];
}

/** Map one translation command to its per-task export and layout flags. */
export function translationOutputSettings(
    mode: TranslationMode,
): TranslationOutputSettings {
    const mono = mode === "mono" || mode === "both";
    const dual = mode !== "mono";

    return {
        mono: String(mono),
        dual: String(dual),
        mono_cut: "false",
        dual_cut: "false",
        crop_compare: "false",
        compare: "false",
        noMono: String(!mono),
        noDual: String(!dual),
        ...(dual ? { dualMode: mode === "dual-tb" ? "TB" : "LR" } : {}),
    };
}
