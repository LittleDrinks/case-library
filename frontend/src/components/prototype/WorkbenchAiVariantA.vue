<script setup>
import { ChevronDown, Paperclip, Send, Sparkles, WandSparkles } from "@lucide/vue";
defineProps({ prompt: { type: String, required: true }, selected: { type: String, required: true } });
const emit = defineEmits(["prompt", "queue"]);
</script>
<template>
  <section class="prototype-ai-panel ai-panel-a">
    <div class="ai-panel-status"><i></i>qwen-plus</div>
    <div class="ai-empty-state"><Sparkles :size="28" /><p>向 AI 提问</p></div>
    <div class="selection-context"><WandSparkles :size="14" /><span>已选择 {{ selected.slice(0, 15) }}...</span><button type="button" aria-label="取消选区"><ChevronDown :size="14" /></button></div>
    <form class="rounded-composer" @submit.prevent="emit('queue')"><textarea :value="prompt" aria-label="描述要修改的内容，或提出问题" placeholder="描述要修改的内容，或提出问题" rows="2" @input="emit('prompt', $event.target.value)"></textarea><footer><button type="button" aria-label="添加附件"><Paperclip :size="16" /></button><span>跟踪修订</span><button class="composer-send" type="submit" aria-label="发送"><Send :size="16" /></button></footer></form>
  </section>
</template>
