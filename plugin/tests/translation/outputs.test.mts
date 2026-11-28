import assert from "node:assert/strict";
import test from "node:test";
import {
    translationOutputSettings,
    translationOutputsForMode,
} from "../../src/translation/outputs.ts";

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

test("combined translation exports and imports both mono and LR dual editions", () => {
    assert.deepEqual(translationOutputSettings("both"), {
        mono: "true",
        dual: "true",
        mono_cut: "false",
        dual_cut: "false",
        crop_compare: "false",
        compare: "false",
        noMono: "false",
        noDual: "false",
        dualMode: "LR",
    });
    assert.deepEqual(translationOutputsForMode("both"), ["mono", "dual"]);
    assert.deepEqual(translationOutputsForMode("dual-lr"), ["dual"]);
    assert.deepEqual(translationOutputsForMode("mono"), ["mono"]);
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
