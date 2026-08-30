<script setup>
import {
  Check, CheckCircle2, CircleAlert, CircleDashed, Database, FileCheck2,
  MessageSquarePlus, RotateCcw, Send, Square, X,
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
  <section class="agent-proto-panel agent-proto-b">
    <header class="timeline-thread-strip">
      <div class="thread-pills">
        <button v-for="thread in threads" :key="thread.id" type="button" :class="{ active: thread.id === activeThread }" @click="emit('select-thread', thread.id)">{{ thread.short }}</button>
      </div>
      <button type="button" class="icon-command" aria-label="新建对话" title="新建对话" @click="emit('new-thread')"><MessageSquarePlus :size="17" /></button>
    </header>

    <div class="timeline-request">
      <small>本次任务</small><p>结合平台资料，把选中的教学目标改得更可操作。</p>
      <span>{{ selected.slice(0, 25) }}...</span>
    </div>

    <ol class="agent-timeline">
      <li class="done"><CheckCircle2 :size="17" /><div><b>理解选区</b><small>教学目的 · 第 1 段</small></div></li>
      <li class="done"><Database :size="17" /><div><b>检索平台资料</b><small>找到 3 条可访问来源</small><button type="button">查看来源</button></div></li>
      <li :class="{ done: scenario === 'complete', active: scenario === 'running', failed: scenario === 'error' }">
        <FileCheck2 v-if="scenario === 'complete'" :size="17" />
        <CircleDashed v-if="scenario === 'running'" :size="17" />
        <CircleAlert v-if="scenario === 'error'" :size="17" />
        <div><b>{{ scenario === 'error' ? '生成修订失败' : '形成修订候选' }}</b><small>{{ scenario === 'running' ? '正在核对原文与来源' : scenario === 'error' ? '模型服务暂时不可用' : '已生成 1 条候选' }}</small></div>
        <button v-if="scenario === 'running'" type="button" @click="emit('stop')"><Square :size="12" />停止</button>
        <button v-if="scenario === 'error'" type="button" @click="emit('retry')"><RotateCcw :size="12" />重试</button>
      </li>
      <li :class="{ pending: scenario !== 'complete', active: scenario === 'complete' }">
        <Check v-if="scenario === 'complete'" :size="17" /><CircleDashed v-else :size="17" />
        <div><b>等待教师确认</b><small>{{ scenario === 'complete' ? '正文尚未修改' : '候选生成后进入确认' }}</small></div>
      </li>
    </ol>

    <article v-if="scenario === 'complete'" class="timeline-artifact">
      <div><del>形成基本判断。</del><ins>辨识责任主体，并提出可执行的使用边界。</ins></div>
      <p>依据 2 条平台资料 · 接受后产生 1 次 revision</p>
      <footer><button type="button" @click="emit('reject')"><X :size="14" />拒绝</button><button type="button" class="primary-command" @click="emit('accept')"><Check :size="14" />接受</button></footer>
    </article>

    <form class="timeline-composer" @submit.prevent="emit('send')">
      <textarea :value="prompt" aria-label="描述下一项任务" placeholder="描述下一项任务" rows="2" @input="emit('prompt', $event.target.value)"></textarea>
      <button type="submit" class="icon-command primary-icon" aria-label="发送" title="发送"><Send :size="16" /></button>
    </form>
  </section>
</template>
