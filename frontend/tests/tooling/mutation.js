import { createHash } from "node:crypto";
import { parse, compileScript, compileTemplate, rewriteDefault, MagicString } from "@vue/compiler-sfc";

export function compileMutationComponent(source, filename) {
  const { descriptor, errors } = parse(source, { filename });
  if (errors.length) throw new AggregateError(errors, `Cannot parse ${filename}`);
  if (!descriptor.scriptSetup) return source;
  const id = createHash("sha256").update(filename).digest("hex").slice(0, 8);
  const script = compileScript(descriptor, { id });
  const template = compileTemplate({
    source: descriptor.template?.content || "", filename, id,
    scoped: descriptor.styles.some(style => style.scoped),
    compilerOptions: { bindingMetadata: script.bindings },
  });
  if (template.errors.length) throw new AggregateError(template.errors, `Cannot compile ${filename}`);
  const code = new MagicString(source);
  for (const block of [descriptor.scriptSetup, descriptor.script, descriptor.template].filter(Boolean)) {
    code.remove(source.lastIndexOf("<", block.loc.start.offset - 1), source.indexOf(">", block.loc.end.offset) + 1);
  }
  const body = `${rewriteDefault(script.content, "__mutationComponent")}\n${template.code.replace("export function render", "function render")}\n__mutationComponent.render = render;\nexport default __mutationComponent;`;
  return code.prepend(`<script>\n${body}\n</script>\n`).toString();
}

export const mutationReporter = {
  onTestRunEnd(modules) {
    const errors = modules.flatMap(module => module.errors());
    if (errors.length) throw new AggregateError(errors, "Mutation test files failed to load");
  },
};
