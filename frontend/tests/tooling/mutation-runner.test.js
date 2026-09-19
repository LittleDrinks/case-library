import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, copyFile, writeFile, readFile, rm, symlink, realpath, access } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = fileURLToPath(new URL("../../", import.meta.url));

for (const status of [0, 42]) test(`mutation runner preserves exit ${status} and removes its private stage`, async () => {
  const fixture = await mkdtemp(path.join(tmpdir(), "mutation-runner-test-"));
  try {
    for (const name of ["src", "public", "tests/tooling", "node_modules/@stryker-mutator/core/bin", "node_modules/@vue"]) {
      await mkdir(path.join(fixture, name), { recursive: true });
    }
    for (const name of ["mutation.js", "run-mutation.js"]) {
      await copyFile(path.join(frontend, "tests/tooling", name), path.join(fixture, "tests/tooling", name));
    }
    await symlink(await realpath(path.join(frontend, "node_modules/@vue/compiler-sfc")), path.join(fixture, "node_modules/@vue/compiler-sfc"));
    await writeFile(path.join(fixture, "package.json"), '{"type":"module"}');
    for (const name of ["vite.config.js", "mutation.config.js"]) await writeFile(path.join(fixture, name), "export default {};");
    await writeFile(path.join(fixture, "stryker.config.json"), "{}");
    const original = '<script setup>defineProps({ name: String });</script><template><span /></template>';
    await writeFile(path.join(fixture, "src/Example.vue"), original);
    const cli = `const fs=require('node:fs');
      const source=fs.readFileSync('src/Example.vue','utf8');
      if(source.includes('defineProps(')) process.exit(99);
      fs.writeFileSync(${JSON.stringify(path.join(fixture, "stage-path"))},process.cwd());
      process.exit(${status});`;
    await writeFile(path.join(fixture, "node_modules/@stryker-mutator/core/bin/stryker.js"), cli);
    const result = spawnSync(process.execPath, [path.join(fixture, "tests/tooling/run-mutation.js")], { encoding: "utf8" });
    assert.equal(result.status, status, result.stderr);
    const stage = await readFile(path.join(fixture, "stage-path"), "utf8");
    await assert.rejects(access(stage), { code: "ENOENT" });
    assert.equal(await readFile(path.join(fixture, "src/Example.vue"), "utf8"), original);
    const scope = JSON.parse(await readFile(path.join(fixture, "reports/mutation/scope.json"), "utf8"));
    assert.equal(scope.files.length, 1);
    assert.notEqual(scope.files[0].sourceSha256, scope.files[0].mutationInputSha256);
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});
