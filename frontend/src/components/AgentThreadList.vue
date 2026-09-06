<script setup>
import { ArrowLeft, LoaderCircle, MessageSquarePlus, Pencil } from "@lucide/vue";
import { ref } from "vue";

defineProps({
  threads: { type: Array, required: true },
  currentId: { type: String, default: null },
  loading: { type: Boolean, default: false },
});
const emit = defineEmits(["back", "select", "create", "rename"]);

const editingId = ref(null);
const editingTitle = ref("");

function activityLabel(thread) {
  const at = thread.updatedAt || thread.createdAt;
  if (!at) return "";
  return new Date(at).toLocaleString("zh-CN", {
    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function startRename(thread) {
  editingId.value = thread.id;
  editingTitle.value = thread.title || "";
}

function confirmRename() {
  const title = editingTitle.value.trim();
  if (editingId.value && title) emit("rename", editingId.value, title);
  editingId.value = null;
}
</script>

<template>
  <div class="agent-thread-list" data-testid="agent-thread-list">
    <header class="agent-thread-list-header">
      <button type="button" data-testid="agent-thread-back" @click="emit('back')">
        <ArrowLeft :size="15" aria-hidden="true" /><span>返回当前对话</span>
      </button>
      <button type="button" data-testid="agent-thread-create" @click="emit('create')">
        <MessageSquarePlus :size="15" aria-hidden="true" /><span>新建对话</span>
      </button>
    </header>
    <p v-if="loading" class="agent-thread-loading">
      <LoaderCircle class="spin" :size="14" aria-hidden="true" />加载中
    </p>
    <ul v-else class="agent-thread-rows">
      <li
        v-for="thread in threads"
        :key="thread.id"
        class="agent-thread-row"
        :data-thread-id="thread.id"
        :data-running="thread.running ? 'true' : 'false'"
      >
        <template v-if="editingId === thread.id">
          <input
            v-model="editingTitle"
            data-testid="agent-thread-rename-input"
            aria-label="对话标题"
            maxlength="60"
            @keydown.enter.prevent="confirmRename"
            @keydown.esc.prevent="editingId = null"
          />
          <button type="button" data-testid="agent-thread-rename-confirm" @click="confirmRename">确定</button>
        </template>
        <template v-else>
          <button
            type="button"
            class="agent-thread-open"
            :class="{ current: thread.id === currentId }"
            data-testid="agent-thread-open"
            @click="emit('select', thread.id)"
          >
            <b>{{ thread.title || "未命名对话" }}</b>
            <span class="agent-thread-meta">
              <span v-if="thread.running" class="agent-thread-running">生成中</span>
              <time>{{ activityLabel(thread) }}</time>
            </span>
          </button>
          <button
            type="button"
            class="agent-thread-rename"
            title="重命名"
            data-testid="agent-thread-rename"
            @click="startRename(thread)"
          >
            <Pencil :size="13" aria-hidden="true" />
          </button>
        </template>
      </li>
    </ul>
  </div>
</template>
