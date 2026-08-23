<script setup>
import { LoaderCircle, ShieldCheck } from "@lucide/vue";
import { onMounted, ref } from "vue";
import SiteHeader from "../components/SiteHeader.vue";
import { api } from "../api.js";
import { session } from "../session.js";

const fallbackModel = ref("");
const availableModels = ref([]);
const configured = ref(false);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

function applySettings(value) {
  fallbackModel.value = value.fallbackModel || "";
  availableModels.value = value.availableModels;
  configured.value = value.configured;
}

async function loadSettings() {
  try { applySettings(await api.adminAISettings()); }
  catch (reason) { error.value = reason.message || "平台 AI 设置加载失败"; }
  finally { loading.value = false; }
}

async function saveSettings() {
  error.value = "";
  notice.value = "";
  saving.value = true;
  try {
    const body = { fallbackModel: fallbackModel.value || null };
    applySettings(await api.saveAdminAISettings(body, session.csrfToken));
    notice.value = "平台 AI 设置已保存";
  } catch (reason) { error.value = reason.message || "平台 AI 设置保存失败"; }
  finally { saving.value = false; }
}

onMounted(loadSettings);
</script>

<template>
  <div class="settings-page">
    <SiteHeader />
    <main id="main-content" class="settings-main">
      <header class="settings-heading">
        <div><span>管理后台</span><h1>平台兜底模型</h1></div>
        <RouterLink :to="{ name: 'ai-settings' }">返回个人设置</RouterLink>
      </header>
      <div v-if="loading" class="settings-state"><LoaderCircle class="spin" :size="20" />正在加载设置</div>
      <form v-else class="settings-form" @submit.prevent="saveSettings">
        <section class="settings-section">
          <header><ShieldCheck :size="18" /><div><h2>兜底模型</h2><p>账号使用自动模式时调用此模型。可选项由服务器部署配置提供。</p></div></header>
          <label><span>兜底模型</span><select v-model="fallbackModel" :disabled="!availableModels.length"><option value="">使用环境默认模型</option><option v-for="item in availableModels" :key="item" :value="item">{{ item }}</option></select></label>
          <p v-if="!availableModels.length" class="settings-hint">服务器尚未配置可用模型列表。</p>
          <p class="settings-hint">服务状态：{{ configured ? "可用" : "尚未完整配置" }}</p>
        </section>
        <p v-if="error" class="settings-message error" role="alert">{{ error }}</p>
        <p v-if="notice" class="settings-message success" role="status">{{ notice }}</p>
        <footer><button class="primary-button" type="submit" :disabled="saving"><LoaderCircle v-if="saving" class="spin" :size="16" />{{ saving ? "正在保存" : "保存平台设置" }}</button></footer>
      </form>
    </main>
  </div>
</template>
