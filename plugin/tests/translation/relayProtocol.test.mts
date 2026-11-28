import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import {
    needsRelayPatch,
    supportsRelayPatch,
} from "../../src/translation/capabilities.ts";

test("custom services require relay support without changing built-in jobs", () => {
    assert.equal(needsRelayPatch({ service: "my-relay" }), true);
    for (const service of ["openai", "openailiked", "deepseek", "ModelScope"]) {
        assert.equal(needsRelayPatch({ service }), false);
    }
    assert.equal(
        needsRelayPatch({
            service: "openai",
            extraData: { zotero_api_format: "responses" },
        }),
        true,
    );
    assert.equal(
        needsRelayPatch({
            service: "openailiked",
            extraData: { zotero_extra_headers: '{"X-Tenant":"test"}' },
        }),
        true,
    );
});

test("the old relay protocol cannot accept updated custom jobs", () => {
    for (const payload of [
        null,
        {},
        { relayPatch: true },
        { relayPatch: true, relayPatchVersion: 1 },
        { relayPatch: true, relayPatchVersion: "2" },
        { relayPatch: false, relayPatchVersion: 2 },
    ]) {
        assert.equal(supportsRelayPatch(payload), false);
    }
    assert.equal(
        supportsRelayPatch({ relayPatch: true, relayPatchVersion: 2 }),
        true,
    );
});

test("an unsupported Server is rejected before the PDF POST", async () => {
    const requests: string[] = [];
    const context = vm.createContext({
        ztoolkit: { log() {} },
        fetch: async (url: string) => {
            requests.push(url);
            assert.ok(url.endsWith("/health"));
            return { ok: true, json: async () => ({ relayPatch: true }) };
        },
    });
    const exports: any = {};
    const source = fs.readFileSync(
        new URL("../../src/translation/serverClient.ts", import.meta.url),
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
        "../utils/locale": { getString: (key: string) => key },
        "./capabilities": {
            needsRelayPatch,
            supportsRelayPatch,
            needsDeepSeekFlashPatch: () => false,
        },
    };
    vm.runInContext(`(function(require, exports) {${js}})`, context)(
        (name: string) => imports[name] ?? {},
        exports,
    );
    await assert.rejects(
        exports.sendRequest(
            { fileName: "paper.pdf", base64: "offline" },
            {
                engine: "pdf2zh_next",
                next_service: "my-relay",
                serverUrl: "http://server.invalid",
            },
            "translate",
            {
                service: "my-relay",
                apiKey: "offline-key",
                apiUrl: "http://relay.invalid/v1",
                model: "offline-model",
            },
        ),
        /operation-error-relay-server/,
    );
    assert.deepEqual(requests, ["http://server.invalid/health"]);
});
