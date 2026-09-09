<script setup>
// 两种候选预览交互嵌入真实工作台；所有采用和批注操作仅保存在本页内存。
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight, Check, MessageSquareText, Sparkles, X } from "@lucide/vue";
import CanvasEditor from "./CanvasEditor.vue";
import { renderMarkdown } from "../lib/markdown.js";
import { api } from "../api.js";
const props = defineProps({ caseRecord: Object });
const route = useRoute(), router = useRouter();
const artifact = ref(null), selected = ref(0), tab = ref("candidate"), comments = ref([]);
const accepted = ref([]), status = ref("待确认"), note = ref(""), panel = ref("candidate");
const variant = computed(() => route.query.variant === "B" ? "B" : "A");
const blocks = computed(() => artifact.value?.blocks || []);
const sections = computed(() => blocks.value.reduce(groupBlock, []));
const current = computed(() => sections.value[selected.value]);
function groupBlock(result, block) {
  if (block.type === "heading" || !result.length) result.push({ title: block.type === "heading" ? block.text : "正文", blocks: [] });
  result.at(-1).blocks.push(block);
  return result;
}
function blockMarkdown(block) {
  if (block.type === "heading") return `${"#".repeat(Math.min(block.level || 2, 3))} ${block.text}`;
  if (block.type === "bullet_list") return block.items.map(x => `- ${x}`).join("\n");
  if (block.type === "ordered_list") return block.items.map((x, i) => `${i + 1}. ${x}`).join("\n");
  if (block.type === "blockquote") return block.paragraphs.map(x => `> ${x}`).join("\n");
  return block.text || "";
}
function sectionHtml(section) { return renderMarkdown(section.blocks.map(blockMarkdown).join("\n\n")); }
async function load() {
  const threads = await api.agentThreads(props.caseRecord.id);
  for (const thread of threads) {
    const snapshot = await api.agentThread(props.caseRecord.id, thread.id);
    const candidate = [...(snapshot.artifacts || [])].reverse().find(x => x.kind === "document");
    if (candidate) { artifact.value = candidate; return; }
  }
}
function locate(index) {
  selected.value = index;
  document.getElementById(`candidate-section-${index}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
}
function switchVariant() { router.replace({ query: { ...route.query, variant: variant.value === "A" ? "B" : "A" } }); }
function acceptAll() { status.value = "已在原型中采用整稿"; accepted.value = sections.value.map((_, i) => i); }
function acceptSection(index) { if (!accepted.value.includes(index)) accepted.value.push(index); }
function addComment() {
  if (!note.value.trim()) return;
  comments.value.push({ section: current.value?.title || "全文", text: note.value.trim() });
  note.value = "";
}
onMounted(load);
</script>

<template>
  <div class="canvas-workspace candidate-prototype">
    <nav class="prototype-outline"><small>候选目录</small><button v-for="(section, i) in sections" :key="i" :class="{ current: selected === i }" @click="locate(i)">{{ section.title }}<Check v-if="accepted.includes(i)" :size="13" /></button></nav>
    <main class="canvas-column prototype-canvas">
      <div class="prototype-preview-bar"><span><Sparkles :size="15" />{{ variant === 'A' ? '全文候选预览' : '逐节审阅候选' }}</span><div v-if="variant === 'A'" class="prototype-segment"><button :class="{ active: tab === 'original' }" @click="tab = 'original'">当前正文</button><button :class="{ active: tab === 'candidate' }" @click="tab = 'candidate'">AI 候选</button></div><span class="prototype-state">{{ status }}</span></div>
      <article class="document-paper prototype-paper">
        <template v-if="variant === 'A' && tab === 'original'"><h1>{{ caseRecord.title }}</h1><CanvasEditor :document="caseRecord.document" :editable="false" /></template>
        <template v-else>
          <div class="prototype-document-note">{{ variant === 'A' ? '完整预览 · 采用前不会修改正文' : '逐节确认 · 绿色区域为建议新增内容' }}</div>
          <p v-if="!artifact">正在读取本案例的完整候选……</p>
          <section v-for="(section, i) in sections" :id="`candidate-section-${i}`" :key="i" class="prototype-section" :class="{ proposed: variant === 'B', focused: selected === i, adopted: accepted.includes(i) }" @click="selected = i">
            <div class="markdown-body" v-html="sectionHtml(section)" />
            <div v-if="variant === 'B'" class="prototype-section-actions"><span>{{ accepted.includes(i) ? '已采用此节' : '建议新增' }}</span><button @click.stop="acceptSection(i)"><Check :size="14" />采用此节</button><button @click.stop="selected = i; panel = 'comments'"><MessageSquareText :size="14" />添加意见</button></div>
          </section>
        </template>
      </article>
    </main>
    <aside class="prototype-assistant">
      <header><button :class="{ active: panel === 'candidate' }" @click="panel = 'candidate'"><Sparkles :size="17" />AI 候选</button><button :class="{ active: panel === 'comments' }" @click="panel = 'comments'"><MessageSquareText :size="17" />批注 <small v-if="comments.length">{{ comments.length }}</small></button></header>
      <div class="prototype-thread">根据我的资料帮我生成一份案例 <span>⌄</span></div>
      <div class="prototype-rail-content">
        <template v-if="panel === 'candidate'">
          <div class="prototype-assistant-label">AI · 全文初稿</div><h2>候选已准备好</h2><p>完整内容已在左侧展开。你可以沿目录逐节阅读，也可以随时切回当前正文。</p>
          <div class="prototype-facts"><span>内容范围</span><b>{{ sections.length }} 个小节</b><span>当前状态</span><b>{{ accepted.length ? `${accepted.length} 节已确认` : '尚未写入正文' }}</b></div>
          <div class="prototype-evidence"><b>审阅时留意</b><p>候选中的事实、数字和引文仍需对照来源核实。“已生成”不代表“已核实”。</p></div>
          <button class="prototype-locate" @click="locate(selected)">定位到「{{ current?.title || '正文' }}」 <ArrowLeft :size="14" /></button>
          <div class="prototype-help"><h3>候选与批注怎么配合？</h3><p>候选回答“准备怎么写”。批注指出“哪一处还需要处理”。对某节有疑问时，可以在该位置留下意见，再回到对话中调整。</p></div>
        </template>
        <template v-else>
          <div class="prototype-assistant-label">当前定位</div><blockquote>{{ current?.title || '全文' }}</blockquote><p class="prototype-muted">先定位原文，再记录具体问题与建议。正式审核的通过或退回仍在页面顶部操作。</p>
          <article v-for="(comment, i) in comments" :key="i" class="prototype-comment"><small>{{ comment.section }}</small><p>{{ comment.text }}</p><span>待处理</span></article>
          <div v-if="!comments.length" class="prototype-empty"><MessageSquareText :size="25" /><p>这个位置还没有批注</p></div>
          <textarea v-model="note" placeholder="例如：这个数据的来源是什么？建议补充出处。" aria-label="原型批注意见" /><button class="prototype-primary" :disabled="!note.trim()" @click="addComment">添加意见</button>
        </template>
      </div>
      <footer><div class="prototype-decisions"><button class="prototype-primary" @click="acceptAll"><Check :size="16" />采用整稿</button><button @click="status = '已在原型中拒绝候选'"><X :size="15" />拒绝</button></div><small>真实正文未修改。原型中的采用和批注只保留在本页。</small></footer>
    </aside>
    <div class="prototype-switcher"><span>交互原型</span><button @click="switchVariant"><ArrowLeft :size="16" /></button><b>{{ variant === 'A' ? 'A · 正文切换预览' : 'B · 原位逐节审阅' }}</b><button @click="switchVariant"><ArrowRight :size="16" /></button><span>{{ status }}</span></div>
  </div>
</template>
<style scoped>
.candidate-prototype { color: var(--ink); }
.prototype-outline { display: flex; flex-direction: column; gap: 12px; padding: 38px 12px 90px 0; overflow: auto; }
.prototype-outline small { color: var(--ink-3); margin-bottom: 16px; }
.prototype-outline button { text-align: left; border: 0; background: none; color: var(--ink-2); line-height: 1.7; padding: 8px 0; display: flex; align-items: center; gap: 6px; }
.prototype-outline button.current { color: var(--brand); }
.prototype-canvas { position: relative; }
.prototype-preview-bar { position: sticky; top: 0; z-index: 3; min-height: 56px; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px 16px; background: #f9f6ef; border: 1px solid var(--line); border-radius: 8px 8px 0 0; font-size: 12px; }
.prototype-preview-bar > span:first-child { display: flex; gap: 6px; align-items: center; }
.prototype-state { color: var(--ink-3); }
.prototype-segment { display: flex; padding: 3px; background: #eee8de; border-radius: 6px; }
.prototype-segment button { border: 0; background: transparent; padding: 6px 10px; border-radius: 4px; color: var(--ink-2); }
.prototype-segment button.active { background: white; color: var(--brand); }
.prototype-paper { border-radius: 0 0 8px 8px; padding: 46px 56px 100px; }
.prototype-paper h1 { font-family: var(--serif); text-align: center; }
.prototype-document-note { text-align: center; color: var(--ink-3); font-size: 12px; margin-bottom: 30px; }
.prototype-section { scroll-margin-top: 85px; padding: 10px 0 20px; }
.prototype-section :deep(.markdown-body) { font-family: var(--serif); font-size: 18px; line-height: 1.9; }
.prototype-section :deep(.markdown-body h1), .prototype-section :deep(.markdown-body h2) { font-size: 23px; margin-bottom: 18px; }
.prototype-section.proposed { background: #f2f8f4; padding: 20px; border-left: 3px solid #bdd7c4; margin: 16px -20px; }
.prototype-section.proposed.focused { border-left-color: #348260; }
.prototype-section.adopted { border-left-color: #348260; }
.prototype-section-actions { display: flex; gap: 10px; justify-content: flex-end; align-items: center; margin-top: 20px; font: 12px/1.6 sans-serif; }
.prototype-section-actions > span { margin-right: auto; color: #348260; }
.prototype-section-actions button, .prototype-decisions button { display: inline-flex; align-items: center; gap: 6px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 6px; background: white; }
.prototype-assistant { min-height: 0; display: flex; flex-direction: column; border: 1px solid var(--line); border-radius: 12px; background: #fcfaf6; overflow: hidden; }
.prototype-assistant header { display: flex; gap: 16px; padding: 0 16px; border-bottom: 1px solid var(--line); }
.prototype-assistant header button { display: flex; align-items: center; gap: 7px; padding: 16px 10px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: var(--ink-2); }
.prototype-assistant header button.active { color: var(--brand); border-bottom-color: var(--brand); }
.prototype-thread { font-size: 12px; padding: 12px 18px; border-bottom: 1px solid var(--line); }
.prototype-thread span { float: right; }
.prototype-rail-content { min-height: 0; overflow: auto; padding: 26px 22px; flex: 1; font-size: 13px; line-height: 1.8; }
.prototype-assistant-label { font-size: 11px; color: var(--ink-3); }
.prototype-rail-content h2 { font-size: 19px; margin: 8px 0 12px; }
.prototype-facts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 20px 0; border-bottom: 1px solid var(--line); }
.prototype-facts span { color: var(--ink-3); }
.prototype-facts b { font-weight: 500; text-align: right; }
.prototype-evidence { background: #f2ece1; border-radius: 7px; padding: 16px; margin: 24px 0; }
.prototype-evidence p { margin-bottom: 0; }
.prototype-locate { display: flex; align-items: center; justify-content: space-between; gap: 6px; width: 100%; text-align: left; border: 1px solid var(--line); padding: 12px; background: white; border-radius: 7px; color: var(--brand); }
.prototype-help { margin-top: 30px; color: var(--ink-2); }
.prototype-help h3 { font-size: 14px; }
.prototype-assistant footer { padding: 18px 22px; border-top: 1px solid var(--line); }
.prototype-decisions { display: flex; gap: 10px; margin-bottom: 12px; }
.prototype-primary, .prototype-decisions .prototype-primary { border: 0; background: var(--brand); color: white; border-radius: 6px; padding: 9px 15px; }
.prototype-primary:disabled { opacity: .5; }
.prototype-assistant footer small, .prototype-muted { color: var(--ink-3); font-size: 11px; }
.prototype-rail-content blockquote { margin: 14px 0; padding: 14px; background: #f2ece1; border-left: 2px solid var(--brand); }
.prototype-empty { text-align: center; padding: 35px 10px; color: var(--ink-3); }
.prototype-rail-content textarea { width: 100%; min-height: 105px; padding: 12px; border: 1px solid var(--line); border-radius: 6px; margin: 12px 0; resize: vertical; background: white; }
.prototype-comment { border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin-top: 12px; background: white; }
.prototype-comment small, .prototype-comment span { font-size: 11px; color: var(--ink-3); }
.prototype-switcher { position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); z-index: 90; display: flex; gap: 12px; align-items: center; padding: 10px 14px; border-radius: 10px; color: white; background: #302c27; box-shadow: 0 4px 22px #0002; font-size: 12px; }
.prototype-switcher > span { color: #c6bbaa; white-space: nowrap; }
.prototype-switcher button { background: transparent; color: white; border: 1px solid #72685a; border-radius: 5px; padding: 4px; display: flex; }
.prototype-switcher b { white-space: nowrap; font-weight: 500; }
@media(max-width: 1000px) { .prototype-outline { display:none; } .prototype-paper { padding: 30px 24px 80px; } }
@media(max-width: 780px) { .candidate-prototype { display: grid; grid-template-columns: 1fr; overflow: auto; } .prototype-assistant { min-height: 500px; } .prototype-preview-bar { flex-wrap: wrap; } .prototype-switcher > span:last-child { display:none; } }
</style>
