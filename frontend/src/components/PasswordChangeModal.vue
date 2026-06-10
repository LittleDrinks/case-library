<template>
  <div class="modal-overlay">
    <div class="modal-panel">
      <div class="modal-header">
        <div class="header-icon">锁</div>
        <h2>修改初始密码</h2>
      </div>
      <p class="modal-desc">
        您的账户当前使用的是初始密码。为保障账户安全，请先修改密码后再继续使用系统。
      </p>
      <form @submit.prevent="handleSubmit">
        <div class="field">
          <label for="pc-username">用户名</label>
          <input
            id="pc-username"
            v-model="username"
            type="text"
            readonly
          />
        </div>
        <div class="field">
          <label for="pc-old">原密码</label>
          <input
            id="pc-old"
            v-model="oldPassword"
            type="password"
            autocomplete="current-password"
            placeholder="请输入当前密码"
            required
          />
        </div>
        <div class="field">
          <label for="pc-new">新密码</label>
          <input
            id="pc-new"
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            placeholder="请输入新密码"
            required
          />
        </div>
        <div class="field">
          <label for="pc-confirm">确认新密码</label>
          <input
            id="pc-confirm"
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            placeholder="请再次输入新密码"
            required
          />
        </div>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <div class="actions">
          <button type="submit" class="btn-primary" :disabled="loading">
            {{ loading ? "提交中..." : "确认修改" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { changePassword, currentUser } from "../api/auth.js";

const emit = defineEmits(["success"]);

const user = computed(() => currentUser());
const username = computed(() => user.value?.username || "");

const oldPassword = ref("");
const newPassword = ref("");
const confirmPassword = ref("");
const loading = ref(false);
const error = ref("");

async function handleSubmit() {
  error.value = "";

  if (newPassword.value !== confirmPassword.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  if (newPassword.value.length < 8) {
    error.value = "新密码长度不能少于8位";
    return;
  }

  loading.value = true;
  const result = await changePassword(
    username.value,
    oldPassword.value,
    newPassword.value
  );
  loading.value = false;

  if (result.success) {
    oldPassword.value = "";
    newPassword.value = "";
    confirmPassword.value = "";
    emit("success");
  } else {
    error.value = result.error || "修改密码失败";
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(29, 35, 47, 0.55);
  backdrop-filter: blur(4px);
}

.modal-panel {
  width: min(440px, 92vw);
  padding: 28px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 20px 60px rgba(29, 35, 47, 0.22);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.header-icon {
  font-size: 22px;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1d232f;
}

.modal-desc {
  margin: 0 0 20px;
  font-size: 14px;
  color: #4b5565;
  line-height: 1.6;
}

.field {
  margin-bottom: 14px;
}

.field label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.field input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font: inherit;
  font-size: 14px;
  color: #1d232f;
  background: #fff;
}

.field input[readonly] {
  background: #f3f4f6;
  color: #6b7280;
}

.field input::placeholder {
  color: #9ca3af;
}

.field input:focus {
  outline: none;
  border-color: #8d1b35;
  box-shadow: 0 0 0 3px rgba(141, 27, 53, 0.1);
}

.error-msg {
  margin-bottom: 16px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 13px;
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  min-height: 40px;
  padding: 0 20px;
  border: 0;
  border-radius: 6px;
  color: #fff;
  background: #8d1b35;
  font: inherit;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary:hover:not(:disabled) {
  background: #74152a;
}
</style>
