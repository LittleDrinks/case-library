import { cp, mkdir, mkdtemp, readFile, readdir, realpath, rm, symlink, writeFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { compileMutationComponent } from "./mutation.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const reports = path.join(root, "reports/mutation");
const stage = await mkdtemp(path.join(tmpdir(), "case-library-mutation-"));
const digest = value => createHash("sha256").update(value).digest("hex");
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
  await prepare();
  process.exitCode = interrupted ?? await run();
} finally {
  await rm(stage, { recursive: true, force: true });
  if (interrupted) process.exitCode = interrupted;
  for (const [signal, handler] of handlers) process.off(signal, handler);
}
