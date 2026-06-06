<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-panel">
      <div class="modal-header">
        <h2>用户登录</h2>
        <button type="button" class="close-btn" @click="$emit('close')">&times;</button>
      </div>
      <form @submit.prevent="handleSubmit">
        <div class="field">
          <label for="login-username">用户名</label>
          <input
            id="login-username"
            v-model="username"
            type="text"
            autocomplete="username"
            placeholder="请输入用户名"
            required
          />
        </div>
        <div class="field">
          <label for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            required
          />
        </div>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <div class="actions">
          <button type="submit" class="btn-primary" :disabled="loading">
            {{ loading ? "登录中..." : "登录" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { login } from "../api/auth.js";

const emit = defineEmits(["close", "success"]);

const username = ref("");
const password = ref("");
const loading = ref(false);
const error = ref("");

async function handleSubmit() {
  error.value = "";
  loading.value = true;
  const result = await login(username.value, password.value);
  loading.value = false;
  if (result.success) {
    username.value = "";
    password.value = "";
    emit("success");
  } else {
    error.value = result.error || "登录失败";
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(29, 35, 47, 0.45);
  backdrop-filter: blur(4px);
}

.modal-panel {
  width: min(420px, 92vw);
  padding: 28px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 20px 60px rgba(29, 35, 47, 0.18);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.modal-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1d232f;
}

.close-btn {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #6b7280;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.close-btn:hover {
  background: #f3f4f6;
  color: #1d232f;
}

.field {
  margin-bottom: 16px;
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
