<script setup>
import { Check, Globe2, Plus, Send, Sparkles, X } from "@lucide/vue";
import { ref } from "vue";
defineProps({ prompt: { type: String, required: true } });
const emit = defineEmits(["prompt", "queue", "accept", "dismiss"]);
const launcherOpen = ref(false);
const webSearchActive = ref(false);

function activateWebSearch() {
  webSearchActive.value = true;
  launcherOpen.value = false;
}
</script>
<template>
  <section class="prototype-ai-panel ai-panel-b">
    <div class="ai-panel-status"><i></i>qwen-plus <span>本次修订</span></div>
    <div class="revision-thread"><p class="thread-request">请让这段目标更具可操作性</p><article class="thread-change"><header><Sparkles :size="15" /><b>建议修订</b></header><p><del>形成基本判断。</del><ins>辨识责任主体，并提出可执行的使用边界。</ins></p><footer><button type="button" @click="emit('dismiss')"><X :size="14" />拒绝</button><button class="accept" type="button" @click="emit('accept')"><Check :size="14" />接受</button></footer></article></div>
    <form class="thread-composer" @submit.prevent="emit('queue')"><textarea :value="prompt" aria-label="结合资料提问或修改选区" placeholder="结合资料提问或修改选区" rows="2" @input="emit('prompt', $event.target.value)"></textarea><footer><div class="composer-launcher"><button class="plus-button" type="button" aria-label="添加上下文" @click="launcherOpen = !launcherOpen"><Plus :size="16" /></button><div v-if="launcherOpen" class="launcher-menu"><button type="button" @click="activateWebSearch"><Globe2 :size="16" /><span><b>联网检索</b><small>查询公开资料并附来源</small></span></button></div></div><span class="material-count">2 份资料</span><span v-if="webSearchActive" class="web-search-chip"><Globe2 :size="13" />联网检索</span><button class="composer-send" type="submit" aria-label="发送"><Send :size="16" /></button></footer></form>
  </section>
</template>
