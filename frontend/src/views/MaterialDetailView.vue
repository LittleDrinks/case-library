<script setup>
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, ExternalLink, Plus } from "@lucide/vue";
import { useRoute } from "vue-router";
import { api } from "../api.js";
import { session } from "../session.js";
import SiteHeader from "../components/SiteHeader.vue";
import MaterialDownloadAction from "../components/MaterialDownloadAction.vue";

const route = useRoute();
const material = ref(null);
const error = ref("");
const busy = ref(false);
const added = ref(false);
const caseId = computed(() => String(route.query.caseId || ""));
const backTo = computed(() => String(route.query.from || "").startsWith("/materials")
  ? String(route.query.from) : { name: "materials" });
const sourceUrl = computed(() => /^https?:\/\//i.test(material.value?.sourceUrl || "")
  ? material.value.sourceUrl : "");

async function load() {
  try { material.value = await api.materialDetail(String(route.params.id)); }
  catch (caught) { error.value = caught.message || "当前账号无法查看此素材"; }
}

async function addToCase() {
  if (busy.value || added.value) return;
  busy.value = true;
  try {
    const current = await api.getCase(caseId.value);
    await api.mountCaseMaterial(caseId.value, material.value.id, current.revision, session.csrfToken);
    added.value = true;
  } catch (caught) { error.value = caught.message || "加入失败"; }
  finally { busy.value = false; }
}

onMounted(load);
</script>

<template>
  <div class="home-page">
    <SiteHeader />
    <main id="main-content" class="material-detail">
      <RouterLink class="material-back" :to="backTo"><ArrowLeft :size="16" />返回素材</RouterLink>
      <p v-if="error" class="error-state" role="alert">{{ error }}</p>
      <article v-if="material">
        <header>
          <span class="material-kind">{{ material.materialType || "学习素材" }}</span>
          <h1>{{ material.title }}</h1>
          <div class="material-detail-meta">
            <span v-if="material.source">{{ material.source }}</span>
            <span>{{ { public: "公开", campus: "校内", private: "受限" }[material.accessLevel] }}</span>
            <span v-if="material.publishedAt">{{ material.publishedAt.slice(0, 10) }}</span>
          </div>
        </header>
        <p v-if="material.summary" class="material-detail-body">{{ material.summary }}</p>
        <div class="material-detail-actions">
          <a v-if="sourceUrl" :href="sourceUrl" target="_blank" rel="noopener noreferrer">原始来源<ExternalLink :size="16" /></a>
          <MaterialDownloadAction :material="material" />
          <button v-if="caseId && session.user" type="button" :disabled="busy || added" @click="addToCase">
            <Plus :size="16" />{{ added ? "已加入当前案例" : busy ? "正在加入" : "加入当前案例" }}
          </button>
        </div>
      </article>
      <p v-else-if="!error" role="status">正在加载</p>
    </main>
  </div>
</template>

<style scoped>
.material-detail { max-width: 1000px; margin: 0 auto; padding: 32px 24px 80px; }
.material-back, .material-detail-actions a, .material-detail-actions button { display: inline-flex; align-items: center; gap: 8px; }
.material-detail article { margin-top: 32px; }
.material-kind { color: var(--brand, #a12327); font-size: 14px; }
.material-detail h1 { font-size: 28px; line-height: 1.5; overflow-wrap: anywhere; margin: 12px 0; }
.material-detail-meta { display: flex; flex-wrap: wrap; gap: 16px; color: #666; font-size: 14px; padding-bottom: 24px; border-bottom: 1px solid #ddd; }
.material-detail-body { white-space: pre-wrap; line-height: 2; padding: 24px 0; }
.material-detail-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 24px; }
.material-detail-actions button { padding: 10px 14px; border: 1px solid #ccc; border-radius: 4px; background: white; }
@media (max-width: 600px) { .material-detail { padding: 24px 16px; } .material-detail h1 { font-size: 22px; } }
</style>
