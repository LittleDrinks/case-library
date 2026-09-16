import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { store } from "./store.js";
import { findTextRange, annotationQuote } from "./text-range.js";

function position(editor, item, laneTop) {
  const range = item.anchorMissing ? null : findTextRange(editor.state.doc, annotationQuote(item), item.range);
  const top = range ? editor.view.coordsAtPos(range.from).top - laneTop : 16;
  return { ...item, range, top: Math.max(0, Math.round(top)) };
}
function stack(items, container, observer) {
  let bottom = container.querySelector(".annotation-draft")?.offsetHeight || -12;
  items.sort((a, b) => a.top - b.top);
  for (const item of items) {
    item.top = Math.max(item.top, bottom + 12);
    const card = container.querySelector(`[data-ann="${item.id}"]`);
    bottom = item.top + (card?.offsetHeight || 36);
    if (card) observer?.observe(card);
  }
  return bottom + 32;
}
function measure(state, editor) {
  state.frame = 0;
  const container = document.querySelector(".ann-lane");
  if (!container || !editor()) return;
  const top = container.getBoundingClientRect().top;
  const items = store.annotations.map((a) => position(editor(), a, top));
  state.lanePlaceholder.value = stack(items, container, state.observer);
  if (JSON.stringify(state.lane.value) !== JSON.stringify(items)) state.lane.value = items;
}
async function observe(state, editor, schedule) {
  await nextTick();
  state.observer = new ResizeObserver(schedule);
  for (const el of document.querySelectorAll(".document-paper, .ann-lane")) state.observer.observe(el);
  state.mutation = new MutationObserver(schedule);
  state.mutation.observe(document.querySelector(".ann-lane"), { childList: true, subtree: true });
  editor()?.on("transaction", schedule);
  schedule();
}
function disconnect(state, editor, schedule) {
  state.observer?.disconnect(); state.mutation?.disconnect();
  cancelAnimationFrame(state.frame); editor()?.off("transaction", schedule);
}
export function useAnnotationLayout(editor) {
  const state = { lane: ref([]), lanePlaceholder: ref(0), frame: 0 };
  const schedule = () => {
    if (!state.frame) state.frame = requestAnimationFrame(() => measure(state, editor));
  };
  onMounted(() => observe(state, editor, schedule));
  watch(() => store.annotations, schedule, { deep: true });
  watch(() => store.ui.expandedAnnId, () => nextTick(schedule));
  onBeforeUnmount(() => disconnect(state, editor, schedule));
  return { lane: state.lane, lanePlaceholder: state.lanePlaceholder, schedule };
}
