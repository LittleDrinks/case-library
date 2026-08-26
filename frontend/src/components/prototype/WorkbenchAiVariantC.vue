<script setup>
import { ExternalLink, FileSearch, Paperclip, Send, Sparkles } from "@lucide/vue";
defineProps({ prompt: { type: String, required: true }, selected: { type: String, required: true } });
const emit = defineEmits(["prompt", "queue"]);
</script>
<template>
  <section class="prototype-ai-panel ai-panel-c">
    <div class="ai-panel-status"><i></i>qwen-plus <span>引用资料后生成</span></div>
    <div class="source-context"><header><FileSearch :size="16" /><b>当前上下文</b></header><p>选区：{{ selected.slice(0, 22) }}...</p><article><span>平台资料</span><b>人工智能赋能教育的伦理边界</b><button type="button" aria-label="查看资料"><ExternalLink :size="14" /></button></article><article><span>已附资料</span><b>课堂教学设计规范（节选）</b><button type="button" aria-label="查看资料"><ExternalLink :size="14" /></button></article></div>
    <div class="source-empty"><Sparkles :size="22" /><p>资料将作为参考，不直接改写正文</p></div>
    <form class="rounded-composer source-composer" @submit.prevent="emit('queue')"><textarea :value="prompt" aria-label="结合资料提问" placeholder="结合资料提问或修改选区" rows="2" @input="emit('prompt', $event.target.value)"></textarea><footer><button type="button" aria-label="添加资料"><Paperclip :size="16" /></button><span>2 份资料</span><button class="composer-send" type="submit" aria-label="发送"><Send :size="16" /></button></footer></form>
  </section>
</template>
