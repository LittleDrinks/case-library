<script setup>
import { Bot, KeyRound, LoaderCircle, RefreshCw, Server } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import SiteHeader from "../components/SiteHeader.vue";
import { api } from "../api.js";
import { session } from "../session.js";

const mode = ref("automatic");
const baseUrl = ref("");
const apiKey = ref("");
const model = ref("");
const hasApiKey = ref(false);
const effectiveModel = ref("");
const effectiveSource = ref("");
const discovered = ref([]);
const loading = ref(true);
const discovering = ref(false);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const savedBaseUrl = ref("");
const custom = computed(() => mode.value === "custom");
const normalizedBaseUrl = computed(() => baseUrl.value.trim().replace(/\/+$/, ""));
const changedBaseUrl = computed(() => (
  hasApiKey.value && normalizedBaseUrl.value !== savedBaseUrl.value
));
const keyRequired = computed(() => !hasApiKey.value || changedBaseUrl.value);
const keyPlaceholder = computed(() => {
  if (!hasApiKey.value) return "首次配置必须填写";
  return changedBaseUrl.value ? "Base URL 变更后必须填写新密钥" : "已保存；留空保持不变";
});
const canDiscover = computed(() => Boolean(baseUrl.value.trim() && apiKey.value.trim()));
const automaticLabel = computed(() => {
  if (effectiveSource.value === "custom") return "保存后使用平台兜底";
  return effectiveModel.value ? `当前 ${effectiveModel.value}` : "平台暂未配置";
});

function applySettings(value) {
  mode.value = value.mode;
  baseUrl.value = value.baseUrl || "";
  model.value = value.model || "";
  hasApiKey.value = value.hasApiKey;
  effectiveModel.value = value.effectiveModel || "";
  effectiveSource.value = value.effectiveSource || "";
  savedBaseUrl.value = (value.baseUrl || "").trim().replace(/\/+$/, "");
}

async function loadSettings() {
  loading.value = true;
  try { applySettings(await api.aiSettings()); }
  catch (reason) { error.value = reason.message || "AI 设置加载失败"; }
  finally { loading.value = false; }
}

async function discoverModels() {
  error.value = "";
  notice.value = "";
  discovering.value = true;
  try {
    const result = await api.discoverAIModels(
      { baseUrl: baseUrl.value.trim(), apiKey: apiKey.value.trim() }, session.csrfToken,
    );
    discovered.value = result.models;
    if (!model.value && result.models.length) model.value = result.models[0];
  } catch (reason) { error.value = reason.message || "无法获取模型列表"; }
  finally { discovering.value = false; }
}

function saveBody() {
  if (!custom.value) return { mode: "automatic" };
  return {
    mode: "custom", baseUrl: normalizedBaseUrl.value,
    apiKey: apiKey.value.trim(), model: model.value.trim(),
  };
}

async function saveSettings() {
  error.value = "";
  notice.value = "";
  if (custom.value && keyRequired.value && !apiKey.value.trim()) {
    error.value = hasApiKey.value
      ? "Base URL 变更后必须填写新的 API Key"
      : "首次配置必须填写 API Key";
    return;
  }
  saving.value = true;
  try {
    applySettings(await api.saveAISettings(saveBody(), session.csrfToken));
    apiKey.value = "";
    notice.value = "个人 AI 设置已保存";
  } catch (reason) { error.value = reason.message || "AI 设置保存失败"; }
  finally { saving.value = false; }
}

onMounted(loadSettings);
</script>

<template>
  <div class="settings-page">
    <SiteHeader />
    <main id="main-content" class="settings-main">
      <header class="settings-heading">
        <div><span>个人偏好</span><h1>AI 模型设置</h1></div>
        <RouterLink v-if="session.user?.role === 'admin'" :to="{ name: 'admin-ai-settings' }">平台兜底模型</RouterLink>
      </header>
      <div v-if="loading" class="settings-state"><LoaderCircle class="spin" :size="20" />正在加载设置</div>
      <form v-else class="settings-form" @submit.prevent="saveSettings">
        <section class="settings-section">
          <header><Bot :size="18" /><div><h2>使用方式</h2><p>自动模式使用管理员指定的兜底模型；自定义配置仅当前账号可用。</p></div></header>
          <div class="mode-control" role="radiogroup" aria-label="AI 使用方式">
            <label><input v-model="mode" type="radio" value="automatic" aria-label="自动选择平台模型" /><span><b>自动选择</b><small>{{ automaticLabel }}</small></span></label>
            <label><input v-model="mode" type="radio" value="custom" aria-label="自定义模型服务" /><span><b>自定义服务</b><small>OpenAI 兼容接口</small></span></label>
          </div>
        </section>
        <section v-if="custom" class="settings-section custom-provider">
          <header><Server :size="18" /><div><h2>服务连接</h2><p>密钥加密保存，页面不会读取或回显已保存的值。</p></div></header>
          <label><span>Base URL</span><input v-model="baseUrl" type="url" placeholder="https://provider.example/v1" required /></label>
          <label><span>API Key</span><div class="secret-input"><KeyRound :size="16" /><input v-model="apiKey" type="password" autocomplete="new-password" :placeholder="keyPlaceholder" :required="keyRequired" /></div></label>
          <div class="discover-row">
            <button class="secondary-button" type="button" :disabled="!canDiscover || discovering" @click="discoverModels"><RefreshCw :class="{ spin: discovering }" :size="15" />{{ discovering ? "正在获取" : "获取可用模型" }}</button>
            <span>获取模型时需重新输入 API Key，不会使用或显示已保存密钥。</span>
          </div>
          <label v-if="discovered.length"><span>可用模型</span><select v-model="model"><option v-for="item in discovered" :key="item" :value="item">{{ item }}</option></select></label>
          <label><span>手动设置模型</span><input v-model="model" name="model" maxlength="200" placeholder="输入模型 ID" required /></label>
        </section>
        <p v-if="error" class="settings-message error" role="alert">{{ error }}</p>
        <p v-if="notice" class="settings-message success" role="status">{{ notice }}</p>
        <footer><button class="primary-button" type="submit" :disabled="saving"><LoaderCircle v-if="saving" class="spin" :size="16" />{{ saving ? "正在保存" : "保存个人设置" }}</button></footer>
      </form>
    </main>
  </div>
</template>
