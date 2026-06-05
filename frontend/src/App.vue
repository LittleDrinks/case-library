<template>
  <main class="shell">
    <section class="panel">
      <p class="eyebrow">Case Library</p>
      <h1>强国有我案例库</h1>
      <p class="summary">
        Vue 3 + Vite 开发环境已接入。后端 API 运行在 FastAPI/MongoDB 容器中。
      </p>

      <div class="status-grid">
        <div>
          <span>Frontend</span>
          <strong>Vue 3</strong>
        </div>
        <div>
          <span>Backend</span>
          <strong>FastAPI</strong>
        </div>
        <div>
          <span>Database</span>
          <strong>MongoDB</strong>
        </div>
      </div>

      <button type="button" @click="loadConstants">
        {{ loading ? "连接中..." : "验证 API" }}
      </button>

      <pre v-if="apiResult">{{ apiResult }}</pre>
    </section>
  </main>
</template>

<script setup>
import { ref } from "vue";

const loading = ref(false);
const apiResult = ref("");

async function loadConstants() {
  loading.value = true;
  apiResult.value = "";
  try {
    const response = await fetch("/api/constants");
    const data = await response.json();
    apiResult.value = JSON.stringify(data, null, 2);
  } catch (error) {
    apiResult.value = `API 连接失败: ${error.message}`;
  } finally {
    loading.value = false;
  }
}
</script>
