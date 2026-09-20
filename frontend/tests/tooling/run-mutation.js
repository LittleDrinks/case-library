import { cp, mkdir, mkdtemp, readFile, readdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const reports = path.join(root, "reports/mutation");
const incrementalCache = path.join(root, ".mutation-cache");
const incrementalReport = path.join(incrementalCache, "stryker-incremental.json");
const incrementalFingerprint = path.join(incrementalCache, "fingerprint.json");
const fingerprintVersion = 1;
const fingerprintFiles = [
  "package.json",
  "package-lock.json",
  "vite.config.js",
  "mutation.config.js",
  "stryker.config.json",
  "node_modules/@stryker-mutator/core/package.json",
  "node_modules/@stryker-mutator/vitest-runner/package.json",
  "node_modules/vitest/package.json",
  "node_modules/@vue/compiler-sfc/package.json",
  "node_modules/vite/package.json",
  "node_modules/@vitejs/plugin-vue/package.json",
];
const fingerprintTrees = ["public", "tests/tooling"];
let stage;
const digest = value => createHash("sha256").update(value).digest("hex");

async function optionalDigest(filename) {
  try {
    return digest(await readFile(path.join(root, filename)));
  } catch (error) {
    if (error.code === "ENOENT") return "missing";
    throw error;
  }
}

async function treeDigest(directory) {
  const files = (await sourceFiles(path.join(root, directory))).sort();
  const entries = await Promise.all(files.map(async filename => [
    path.relative(root, filename).split(path.sep).join("/"),
    digest(await readFile(filename)),
  ]));
  return digest(JSON.stringify(entries));
}

async function currentFingerprint() {
  const files = Object.fromEntries(await Promise.all(
    fingerprintFiles.map(async filename => [filename, await optionalDigest(filename)]),
  ));
  const trees = Object.fromEntries(await Promise.all(
    fingerprintTrees.map(async directory => [directory, await treeDigest(directory)]),
  ));
  return digest(JSON.stringify({ fingerprintVersion, node: process.version, files, trees }));
}

function isRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function isIncrementalReport(value) {
  if (!isRecord(value)) return false;
  if (!isRecord(value.files)) return false;
  for (const file of Object.values(value.files)) {
    if (!isRecord(file)) return false;
    if (typeof file.source !== "string") return false;
    if (!Array.isArray(file.mutants)) return false;
  }
  if (value.testFiles === undefined) return true;
  if (!isRecord(value.testFiles)) return false;
  return Object.values(value.testFiles).every(file => (
    isRecord(file) && Array.isArray(file.tests)
  ));
}

async function removeInvalidIncrementalReport() {
  try {
    const report = JSON.parse(await readFile(incrementalReport, "utf8"));
    if (!isIncrementalReport(report)) await rm(incrementalReport, { force: true });
  } catch (error) {
    if (error.code === "ENOENT") return;
    if (error instanceof SyntaxError) {
      await rm(incrementalReport, { force: true });
      return;
    }
    throw error;
  }
}

async function refreshIncrementalCache() {
  const fingerprint = await currentFingerprint();
  let previous;
  try {
    const metadata = JSON.parse(await readFile(incrementalFingerprint, "utf8"));
    if (isRecord(metadata) && metadata.fingerprintVersion === fingerprintVersion) {
      previous = metadata.fingerprint;
    }
  } catch (error) {
    if (error.code !== "ENOENT" && !(error instanceof SyntaxError)) throw error;
  }
  if (previous !== fingerprint) {
    await rm(incrementalCache, { recursive: true, force: true });
    await mkdir(incrementalCache, { recursive: true });
    await writeFile(incrementalFingerprint, JSON.stringify({ fingerprintVersion, fingerprint }, null, 2));
    return;
  }
  await removeInvalidIncrementalReport();
}

async function configureIncremental(config) {
  if (process.argv.length !== 2) {
    config.incremental = false;
    delete config.incrementalFile;
    return;
  }
  await refreshIncrementalCache();
  config.incremental = true;
  config.incrementalFile = incrementalReport;
}
let child;
let interrupted;
const handlers = Object.entries({ SIGINT: 130, SIGTERM: 143, SIGHUP: 129 }).map(([signal, code]) => {
  const handler = () => {
    interrupted = code;
    if (!child?.pid) return;
    try { process.kill(-child.pid, signal); } catch (error) { if (error.code !== "ESRCH") throw error; }
  };
  process.on(signal, handler);
  return [signal, handler];
});

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const lists = await Promise.all(entries.map(entry => {
    const filename = path.join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(filename) : [filename];
  }));
  return lists.flat();
}

async function prepare() {
  const { compileMutationComponent } = await import("./mutation.js");
  await mkdir(reports, { recursive: true });
  for (const filename of ["src", "public", "tests/tooling", "package.json", "vite.config.js", "mutation.config.js", "stryker.config.json"]) {
    await mkdir(path.dirname(path.join(stage, filename)), { recursive: true });
    await cp(path.join(root, filename), path.join(stage, filename), { recursive: true });
  }
  const inventory = [];
  for (const filename of await sourceFiles(path.join(stage, "src"))) {
    if (!/\.(js|vue)$/.test(filename) || filename.endsWith(".test.js")) continue;
    const relative = path.relative(stage, filename).split(path.sep).join("/");
    const source = await readFile(filename, "utf8");
    const compiled = filename.endsWith(".vue") ? compileMutationComponent(source, relative) : source;
    await writeFile(filename, compiled);
    inventory.push({ file: relative, sourceSha256: digest(source), mutationInputSha256: digest(compiled) });
  }
  await cp(path.join(root, "src"), path.join(reports, "original-src"), { recursive: true });
  await cp(path.join(stage, "src"), path.join(reports, "compiled-src"), { recursive: true });
  await writeFile(path.join(reports, "scope.json"), JSON.stringify({
    representation: "Vue compiler output including script bindings and template render functions; JS unchanged",
    files: inventory,
  }, null, 2));
  await symlink(await realpath(path.join(root, "node_modules")), path.join(stage, "node_modules"), "dir");
  const config = JSON.parse(await readFile(path.join(stage, "stryker.config.json"), "utf8"));
  config.jsonReporter = { fileName: path.join(reports, "mutation.json") };
  await configureIncremental(config);
  await writeFile(path.join(stage, "stryker.config.json"), JSON.stringify(config, null, 2));
}

async function run() {
  const cli = path.join(root, "node_modules/@stryker-mutator/core/bin/stryker.js");
  child = spawn(process.execPath, [cli, "run", ...process.argv.slice(2)], {
    cwd: stage, stdio: "inherit", detached: true,
  });
  const status = await new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", code => resolve(code ?? 1));
  });
  return interrupted ?? status;
}

try {
  await rm(reports, { recursive: true, force: true });
  stage = await mkdtemp(path.join(tmpdir(), "case-library-mutation-"));
  await prepare();
  process.exitCode = interrupted ?? await run();
} finally {
  if (stage) await rm(stage, { recursive: true, force: true });
  if (interrupted) process.exitCode = interrupted;
  for (const [signal, handler] of handlers) process.off(signal, handler);
}
