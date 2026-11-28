import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

const taskStatusSource = fs.readFileSync(
    new URL("../../src/translation/serverClient.ts", import.meta.url),
    "utf8",
);
const taskStatusExports: any = {};
vm.runInNewContext(
    "(function(require, exports) {" +
        ts.transpileModule(taskStatusSource, {
            compilerOptions: { module: ts.ModuleKind.CommonJS },
        }).outputText +
        "})",
)(() => ({}), taskStatusExports);
const { taskFinishedWithoutFiles } = taskStatusExports;

test("recognizes only matching successful tasks without files", () => {
    assert.equal(
        taskFinishedWithoutFiles(
            { taskId: "task-1", finished: true, status: "完成" },
            "task-1",
        ),
        true,
    );
    assert.equal(
        taskFinishedWithoutFiles(
            {
                taskId: "task-1",
                finished: true,
                status: "完成",
                fileList: ["done.pdf"],
            },
            "task-1",
        ),
        false,
    );
    assert.equal(
        taskFinishedWithoutFiles(
            { taskId: "task-1", finished: true, status: "失败" },
            "task-1",
        ),
        false,
    );
    assert.equal(
        taskFinishedWithoutFiles(
            { taskId: "another", finished: true, status: "完成" },
            "task-1",
        ),
        false,
    );
});
