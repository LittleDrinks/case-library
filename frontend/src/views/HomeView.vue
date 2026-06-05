<template>
  <div class="view-home">
    <div class="hero">
      <h1>欢迎来到强国有我思政案例库</h1>
      <p class="hero-desc">
        上海大学思政案例库是汇集优质思政教学案例的学术资源平台。
      </p>
    </div>

    <div class="diagnostic-card">
      <div class="diagnostic-header">
        <h2>系统状态诊断</h2>
        <button type="button" class="btn-primary" :disabled="loading" @click="checkApi">
          {{ loading ? "请求中..." : "验证 API 连接" }}
        </button>
      </div>
      <div v-if="error" class="diagnostic-error">
        {{ error }}
      </div>
      <pre v-if="result">{{ result }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { fetchConstants } from "../api/auth.js";

const loading = ref(false);
const result = ref("");
const error = ref("");

async function checkApi() {
  loading.value = true;
  result.value = "";
  error.value = "";
  try {
    const data = await fetchConstants();
    result.value = JSON.stringify(data, null, 2);
  } catch (err) {
    error.value = err.message || "API 请求失败";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.view-home {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 24px;
}

.hero {
  margin-bottom: 32px;
}

.hero h1 {
  margin: 0 0 12px;
  font-size: 32px;
  line-height: 1.3;
  color: #1d232f;
}

.hero-desc {
  margin: 0;
  font-size: 16px;
  color: #4b5565;
  line-height: 1.7;
}

.diagnostic-card {
  padding: 24px;
  border: 1px solid rgba(29, 35, 47, 0.12);
  border-radius: 8px;
  background: #fff;
}

.diagnostic-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.diagnostic-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1d232f;
}

.diagnostic-error {
  padding: 12px 16px;
  border-radius: 6px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 14px;
}

pre {
  max-height: 400px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  border-radius: 6px;
  background: #1d232f;
  color: #f8fafc;
  font-size: 13px;
  line-height: 1.6;
}

.btn-primary {
  min-height: 36px;
  padding: 0 16px;
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
