import { readFileSync, readdirSync } from "node:fs"
import { extname, join, relative } from "node:path"
import process from "node:process"
import { parse } from "@babel/parser"
import { parse as parseVue } from "@vue/compiler-sfc"

const frontendRoot = new URL(".", import.meta.url).pathname
const extensions = new Set([".js", ".mjs", ".vue"])
const functionTypes = new Set([
  "ArrowFunctionExpression", "FunctionDeclaration", "FunctionExpression",
  "ObjectMethod", "ClassMethod", "ClassPrivateMethod",
])

function filesUnder(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? filesUnder(path) : [path]
  })
}

function functionName(node) {
  if (node.id?.name) return node.id.name
  if (node.key?.name) return node.key.name
  return node.type === "ArrowFunctionExpression" ? "<arrow>" : "<anonymous>"
}

function visit(node, file, violations) {
  if (!node || typeof node !== "object") return
  if (functionTypes.has(node.type)) {
    const lines = node.loc.end.line - node.loc.start.line + 1
    if (lines >= 20) violations.push(`${file}:${node.loc.start.line} ${functionName(node)} (${lines} lines)`)
  }
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((child) => visit(child, file, violations))
    else if (value?.type) visit(value, file, violations)
  }
}

function parseScript(source, filename, startLine = 1) {
  return parse(source, {
    sourceType: "module", sourceFilename: filename, startLine,
    plugins: ["jsx", "topLevelAwait"],
  })
}

function vueScripts(source, filename) {
  const result = parseVue(source, { filename })
  if (result.errors.length) throw new Error(result.errors.join("\n"))
  return [result.descriptor.script, result.descriptor.scriptSetup].filter(Boolean)
}

function inspect(file, violations) {
  const source = readFileSync(file, "utf8")
  const name = relative(frontendRoot, file)
  if (extname(file) !== ".vue") return visit(parseScript(source, name), name, violations)
  for (const block of vueScripts(source, name)) {
    visit(parseScript(block.content, name, block.loc.start.line), name, violations)
  }
}

function main() {
  const roots = [join(frontendRoot, "src"), join(frontendRoot, "tests")]
  const ownFile = new URL(import.meta.url).pathname
  const files = [ownFile, ...roots.flatMap(filesUnder).filter((file) => extensions.has(extname(file)))]
  const violations = []
  for (const file of files) inspect(file, violations)
  if (!violations.length) return console.log("Function line check passed (maximum 19 lines).")
  console.error(["Functions must be shorter than 20 lines:", ...violations].join("\n"))
  process.exitCode = 1
}

main()
