import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, mkdir, copyFile, writeFile, readFile, readdir, rm, symlink, realpath, access } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = fileURLToPath(new URL("../../", import.meta.url));

async function makeRunnerFixture(prefix) {
  const fixture = await mkdtemp(path.join(tmpdir(), prefix));
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
  return { fixture, original };
}

async function installFakeCli(fixture, status = 0, failedReport) {
  const reportWrite = failedReport === undefined
    ? ""
    : `if (config.incrementalFile) fs.writeFileSync(config.incrementalFile, ${JSON.stringify(failedReport)});`;
  const cli = `const fs=require('node:fs');
    const source=fs.readFileSync('src/Example.vue','utf8');
    if(source.includes('defineProps(')) process.exit(99);
    const config=JSON.parse(fs.readFileSync('stryker.config.json','utf8'));
    const report=config.incrementalFile && fs.existsSync(config.incrementalFile);
    fs.writeFileSync(${JSON.stringify(path.join(fixture, "config-seen.json"))},JSON.stringify({...config,incrementalReportExists:report}));
    ${reportWrite}
    fs.writeFileSync(${JSON.stringify(path.join(fixture, "stage-path"))},process.cwd());
    process.exit(${status});`;
  await writeFile(path.join(fixture, "node_modules/@stryker-mutator/core/bin/stryker.js"), cli);
}

function runRunner(fixture, args = []) {
  return spawnSync(process.execPath, [path.join(fixture, "tests/tooling/run-mutation.js"), ...args], { encoding: "utf8" });
}

for (const status of [0, 42]) test(`mutation runner preserves exit ${status} and removes its private stage`, async () => {
  const { fixture, original } = await makeRunnerFixture("mutation-runner-test-");
  try {
    await mkdir(path.join(fixture, "reports/mutation/original-src"), { recursive: true });
    await writeFile(path.join(fixture, "reports/mutation/mutation.json"), '{"oldSuccess":true}');
    await writeFile(path.join(fixture, "reports/mutation/original-src/removed.js"), "stale");
    await installFakeCli(fixture, status);
    const result = runRunner(fixture);
    assert.equal(result.status, status, result.stderr);
    const stage = await readFile(path.join(fixture, "stage-path"), "utf8");
    await assert.rejects(access(stage), { code: "ENOENT" });
    await assert.rejects(access(path.join(fixture, "reports/mutation/mutation.json")), { code: "ENOENT" });
    await assert.rejects(access(path.join(fixture, "reports/mutation/original-src/removed.js")), { code: "ENOENT" });
    assert.equal(await readFile(path.join(fixture, "src/Example.vue"), "utf8"), original);
    const scope = JSON.parse(await readFile(path.join(fixture, "reports/mutation/scope.json"), "utf8"));
    assert.equal(scope.files.length, 1);
    assert.notEqual(scope.files[0].sourceSha256, scope.files[0].mutationInputSha256);
    const config = JSON.parse(await readFile(path.join(fixture, "config-seen.json"), "utf8"));
    assert.equal(config.incremental, true);
    assert.match(config.incrementalFile, /[\\/]\.mutation-cache[\\/]stryker-incremental\.json$/);
    await access(path.join(fixture, ".mutation-cache/fingerprint.json"));
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});


test("stale incremental cache is replaced when its fingerprint changes", async () => {
  const { fixture } = await makeRunnerFixture("mutation-incremental-cache-test-");
  try {
    const cache = path.join(fixture, ".mutation-cache");
    await mkdir(path.join(cache, "stale-directory"), { recursive: true });
    await writeFile(path.join(cache, "stryker-incremental.json"), '{"stale":true}');
    await writeFile(path.join(cache, "stale-directory/old"), "stale");
    await writeFile(path.join(cache, "fingerprint.json"), '{"fingerprintVersion":0,"fingerprint":"stale"}');
    await installFakeCli(fixture);
    const result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const config = JSON.parse(await readFile(path.join(fixture, "config-seen.json"), "utf8"));
    assert.equal(config.incrementalReportExists, false);
    await assert.rejects(access(path.join(cache, "stryker-incremental.json")), { code: "ENOENT" });
    await assert.rejects(access(path.join(cache, "stale-directory")), { code: "ENOENT" });
    const fingerprint = JSON.parse(await readFile(path.join(cache, "fingerprint.json"), "utf8"));
    assert.equal(fingerprint.fingerprintVersion, 1);
    assert.notEqual(fingerprint.fingerprint, "stale");
    assert.deepEqual(await readdir(cache), ["fingerprint.json"]);
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

for (const [label, invalidReport] of [
  ["truncated", '{"files":'],
  ["partial", '{"files":{"src/Example.js":{"mutants":[]}}}'],
]) test(`invalid ${label} incremental report from failed run is discarded`, async () => {
  const { fixture } = await makeRunnerFixture(`mutation-invalid-report-${label}-test-`);
  try {
    await installFakeCli(fixture, 42, invalidReport);
    let result = runRunner(fixture);
    assert.equal(result.status, 42, result.stderr);
    const report = path.join(fixture, ".mutation-cache/stryker-incremental.json");
    assert.equal(await readFile(report, "utf8"), invalidReport);
    await installFakeCli(fixture);
    result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const config = JSON.parse(await readFile(path.join(fixture, "config-seen.json"), "utf8"));
    assert.equal(config.incrementalReportExists, false);
    await assert.rejects(access(report), { code: "ENOENT" });
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

for (const relative of ["public/asset.txt", "tests/tooling/helper.js", "mutation.config.js"]) test(`managed cache invalidates when ${relative} changes`, async () => {
  const { fixture } = await makeRunnerFixture("mutation-input-fingerprint-test-");
  try {
    const input = path.join(fixture, relative);
    await mkdir(path.dirname(input), { recursive: true });
    await writeFile(input, "before");
    await installFakeCli(fixture);
    let result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const report = path.join(fixture, ".mutation-cache/stryker-incremental.json");
    await writeFile(report, '{"files":{}}');
    await writeFile(input, "after");
    await installFakeCli(fixture);
    result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const config = JSON.parse(await readFile(path.join(fixture, "config-seen.json"), "utf8"));
    assert.equal(config.incrementalReportExists, false);
    await assert.rejects(access(report), { code: "ENOENT" });
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test("source and test changes remain eligible for native incremental diffing", async () => {
  const { fixture } = await makeRunnerFixture("mutation-native-source-test-test-");
  try {
    await writeFile(path.join(fixture, "src/Example.test.js"), "export const caseValue = 1;");
    await installFakeCli(fixture);
    let result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const report = path.join(fixture, ".mutation-cache/stryker-incremental.json");
    await writeFile(report, '{"files":{}}');
    await writeFile(path.join(fixture, "src/Example.vue"), "<template><span>changed</span></template>");
    await writeFile(path.join(fixture, "src/Example.test.js"), "export const caseValue = 2;");
    await installFakeCli(fixture);
    result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const config = JSON.parse(await readFile(path.join(fixture, "config-seen.json"), "utf8"));
    assert.equal(config.incremental, true);
    assert.equal(config.incrementalReportExists, true);
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test("CLI scope overrides bypass the managed incremental cache", async () => {
  const { fixture } = await makeRunnerFixture("mutation-cli-override-test-");
  try {
    await installFakeCli(fixture);
    let result = runRunner(fixture);
    assert.equal(result.status, 0, result.stderr);
    const cacheReport = path.join(fixture, ".mutation-cache/stryker-incremental.json");
    await writeFile(cacheReport, '{"files":{}}');
    result = runRunner(fixture, ["--mutate", "src/Example.vue"]);
    assert.equal(result.status, 0, result.stderr);
    const config = JSON.parse(await readFile(path.join(fixture, "config-seen.json"), "utf8"));
    assert.equal(config.incremental, false);
    assert.equal("incrementalFile" in config, false);
    assert.equal(await readFile(cacheReport, "utf8"), '{"files":{}}');
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

for (const failure of ["compiler import", "temporary directory"]) test(`bootstrap failure in ${failure} invalidates old results`, async () => {
  const fixture = await mkdtemp(path.join(tmpdir(), "mutation-bootstrap-test-"));
  try {
    await mkdir(path.join(fixture, "tests/tooling"), { recursive: true });
    await mkdir(path.join(fixture, "reports/mutation"), { recursive: true });
    const temporary = path.join(fixture, "temporary");
    await mkdir(temporary);
    for (const name of ["mutation.js", "run-mutation.js"]) {
      await copyFile(path.join(frontend, "tests/tooling", name), path.join(fixture, "tests/tooling", name));
    }
    await writeFile(path.join(fixture, "package.json"), '{"type":"module"}');
    await writeFile(path.join(fixture, "reports/mutation/mutation.json"), '{"oldSuccess":true}');
    const result = spawnSync(process.execPath, [path.join(fixture, "tests/tooling/run-mutation.js")], {
      encoding: "utf8",
      env: { ...process.env, TMPDIR: failure === "compiler import" ? temporary : path.join(fixture, "missing") },
    });
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, failure === "compiler import" ? /ERR_MODULE_NOT_FOUND/ : /ENOENT/);
    await assert.rejects(access(path.join(fixture, "reports/mutation/mutation.json")), { code: "ENOENT" });
    assert.deepEqual(await readdir(temporary), []);
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});
