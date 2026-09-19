import assert from "node:assert/strict";
import { test } from "node:test";
import { parse, compileScript } from "@vue/compiler-sfc";
import { compileMutationComponent, mutationReporter } from "./mutation.js";

const source = `<script setup>
const props = defineProps({ enabled: { type: Boolean, default: false } });
const filters = defineModel('filters', { type: Object, required: true });
const value = 3;
</script><template><span>{{ value }}{{ filters.tagIds }}</span></template>`;

test("Vue macros become mutable runtime declarations with setup bindings retained", () => {
  const compiled = compileMutationComponent(source, "src/Example.vue");
  const { descriptor, errors } = parse(compiled);
  assert.deepEqual(errors, []);
  assert.equal(descriptor.scriptSetup, null);
  assert.doesNotThrow(() => compileScript(descriptor, { id: "probe" }));
  assert.match(compiled, /"filters":/);
  assert.match(compiled, /useModel/);
  assert.match(compiled, /__isScriptSetup/);
  assert.match(compiled, /\$setup\.value/);
  assert.doesNotMatch(compiled, /defineModel\(/);
});

test("ordinary components need no compiler macro transformation", () => {
  const ordinary = '<script>export default {props: ["name"]}</script>';
  assert.equal(compileMutationComponent(ordinary, "Example.vue"), ordinary);
});

for (const script of ["", '<script>export default { props: ["ready"] };</script>']) {
  test(`template logic becomes JavaScript with ${script ? "ordinary script" : "no script"}`, () => {
    const compiled = compileMutationComponent(`${script}<template><span>{{ ready ? 'yes' : 'no' }}</span></template>`, "Choice.vue");
    const { descriptor, errors } = parse(compiled);
    assert.deepEqual(errors, []);
    assert.equal(descriptor.template, null);
    assert.match(descriptor.script.content, /\? 'yes' : 'no'/);
    assert.doesNotThrow(() => compileScript(descriptor, { id: "probe" }));
  });
}

test("invalid components fail instead of disappearing from the mutation scope", () => {
  assert.throws(() => compileMutationComponent('<script setup>const = ;</script>', "Broken.vue"));
});

test("file loading failures cannot be reported as a successful mutation baseline", () => {
  const failure = new Error("Cannot resolve component import");
  assert.throws(() => mutationReporter.onTestRunEnd([
    { errors: () => [] }, { errors: () => [failure] },
  ]), error => error instanceof AggregateError && error.errors.includes(failure));
  assert.doesNotThrow(() => mutationReporter.onTestRunEnd([{ errors: () => [] }]));
});
