<script setup>
import {
  Check, ChevronDown, CircleAlert, ExternalLink, Plus,
  RotateCcw, Search, Send, Square, X,
} from "@lucide/vue";

defineProps({
  activeThread: { type: String, required: true },
  prompt: { type: String, required: true },
  scenario: { type: String, required: true },
  selected: { type: String, required: true },
  threads: { type: Array, required: true },
});
const emit = defineEmits(["accept", "new-thread", "prompt", "reject", "retry", "select-thread", "send", "stop"]);
</script>

<template>
  <section class="agent-proto-panel agent-proto-c">
    <aside class="persistent-thread-list">
      <header><b>对话</b><button type="button" aria-label="新建对话" title="新建对话" @click="emit('new-thread')"><Plus :size="15" /></button></header>
      <button v-for="thread in threads" :key="thread.id" type="button" :class="{ active: thread.id === activeThread }" @click="emit('select-thread', thread.id)">
        <span>{{ thread.short }}</span><small>{{ thread.time }}</small>
      </button>
    </aside>

    <div class="split-conversation">
      <header><span><small>当前对话</small><b>{{ threads.find((item) => item.id === activeThread)?.title }}</b></span><button type="button" aria-label="对话操作" title="对话操作"><ChevronDown :size="15" /></button></header>
      <div class="compact-messages">
        <p class="compact-user">把选中的教学目标改得更可操作。</p>
        <article class="compact-assistant">
          <p>建议将抽象的“形成判断”改为可观察的学习任务。</p>
          <details class="compact-tool"><summary><Search :size="13" />平台检索 · 3 条来源</summary><span>课堂治理、学术诚信、教学目标</span></details>
          <button class="compact-source" type="button">[1] 教育伦理边界 <ExternalLink :size="11" /></button>
        </article>

        <article v-if="scenario === 'complete'" class="compact-artifact">
          <small>修订候选</small><del>形成基本判断。</del><ins>辨识责任主体，并提出可执行的使用边界。</ins>
          <footer><button type="button" aria-label="拒绝" title="拒绝" @click="emit('reject')"><X :size="14" /></button><button type="button" class="primary-command" @click="emit('accept')"><Check :size="13" />接受</button></footer>
        </article>
        <article v-if="scenario === 'running'" class="compact-status"><span class="activity-dot"></span><div><b>正在生成</b><small>已保存当前进度</small></div><button type="button" aria-label="停止" title="停止" @click="emit('stop')"><Square :size="12" /></button></article>
        <article v-if="scenario === 'error'" class="compact-status compact-error"><CircleAlert :size="15" /><div><b>生成失败</b><small>对话与来源未丢失</small></div><button type="button" aria-label="重试" title="重试" @click="emit('retry')"><RotateCcw :size="12" /></button></article>
      </div>

      <form class="split-composer" @submit.prevent="emit('send')">
        <span>选区 · {{ selected.slice(0, 11) }}...</span>
        <textarea :value="prompt" aria-label="继续提问" placeholder="继续提问" rows="2" @input="emit('prompt', $event.target.value)"></textarea>
        <button type="submit" class="icon-command primary-icon" aria-label="发送" title="发送"><Send :size="15" /></button>
      </form>
    </div>
  </section>
</template>
