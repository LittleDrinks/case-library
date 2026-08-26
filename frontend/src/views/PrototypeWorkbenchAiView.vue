<script setup>
// Three AI-panel studies on the existing workbench structure, switchable with ?variant=A|B|C.
import { CheckCircle2, ChevronLeft, ClipboardCheck, Download, History, Paperclip, Sparkles } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import PrototypeVariantSwitcher from "../components/PrototypeVariantSwitcher.vue";
import WorkbenchAiVariantA from "../components/prototype/WorkbenchAiVariantA.vue";
import WorkbenchAiVariantB from "../components/prototype/WorkbenchAiVariantB.vue";
import WorkbenchAiVariantC from "../components/prototype/WorkbenchAiVariantC.vue";
const route = useRoute(); const router = useRouter(); const prompt = ref(""); const action = ref("等待选择操作");
const selected = "形成对学术诚信、数据安全与教师责任的基本判断。";
const variant = computed(() => ["A", "B", "C"].includes(route.query.variant) ? route.query.variant : "B");
const components = { A: WorkbenchAiVariantA, B: WorkbenchAiVariantB, C: WorkbenchAiVariantC };
function setVariant(next) { router.replace({ query: { ...route.query, variant: next } }); }
function setPrompt(value) { prompt.value = value; }
function queue() { action.value = prompt.value ? `已准备生成：${prompt.value}` : "已准备围绕选区生成候选"; }
function accept() { action.value = "已接受候选，保留本次修订快照"; }
function dismiss() { action.value = "已拒绝候选，正文未修改"; }
watch(variant, () => { action.value = `正在查看方案 ${variant.value}`; }, { immediate: true });
</script>
<template>
  <div class="prototype-workbench-page">
    <header class="prototype-site-header"><div class="prototype-brand"><span class="brand-mark">上大</span><b>“强国有我”思政案例库</b></div><nav><span>首页</span><span>我的案例</span><span>资源检索</span><span>管理后台</span></nav><div class="prototype-account">演示管理员</div></header>
    <header class="prototype-workspace-header"><div><span>我的案例</span><i>/</i><b>AI 进课堂案例</b></div><p><em>草稿</em> 已保存</p><div><button type="button" aria-label="AI"><Sparkles :size="17" /></button><button type="button" aria-label="历史版本"><History :size="17" /></button><button type="button" aria-label="附件"><Paperclip :size="17" /></button><button type="button" aria-label="提交前自检"><ClipboardCheck :size="17" /></button><button type="button" aria-label="导出"><Download :size="17" /></button><button class="prototype-submit" type="button">提交审核</button></div></header>
    <div class="prototype-workbench-layout"><aside class="prototype-outline"><p>一、教学说明<br />（800字左右）</p><p>（一）教学目的</p><p>（二）阅读思考题<br />（2～3个）</p><p>（三）教学安排</p><p>（四）注意事项</p><p>二、文本内容<br />（2500字左右）</p><button type="button" aria-label="收起大纲"><ChevronLeft :size="17" /></button></aside><main class="prototype-canvas"><article class="prototype-document"><div class="prototype-toolbar"><b>B</b><b>H₂</b><b>¶</b><b>☷</b><b>1.</b></div><h1>生成式人工智能进课堂：<br />使用边界与课堂治理研讨</h1><div class="prototype-byline">课程未设置　教学案例</div><h2>一、教学说明（800字左右）</h2><h3>（一）教学目的</h3><p>帮助学生识别人工智能辅助学习的合理边界，<mark>{{ selected }}</mark></p><h3>（二）阅读思考题（2～3个）</h3><p>学生以小组为单位分析真实课堂案例，比较不同角色的责任，并形成一份可执行的课堂使用约定。</p><h3>（三）教学安排</h3><p>围绕技术便利、学术诚信、数据安全与教师责任展开研讨。</p></article></main><aside class="prototype-rail"><nav class="prototype-rail-tabs"><button class="active" type="button"><Sparkles :size="17" />AI</button><button type="button">批注</button><button type="button"><Paperclip :size="16" />附件</button></nav><component :is="components[variant]" :selected="selected" :prompt="prompt" @prompt="setPrompt" @queue="queue" @accept="accept" @dismiss="dismiss" /></aside></div>
    <output class="prototype-state"><CheckCircle2 :size="15" /><span>{{ action }}</span><span>选区：{{ selected.slice(0, 12) }}...</span></output><PrototypeVariantSwitcher :variant="variant" @change="setVariant" />
  </div>
</template>
