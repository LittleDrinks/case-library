<script setup>
import { computed, ref, watch } from "vue";
import { AlertTriangle, ArrowLeft, CalendarDays, ExternalLink, FileText, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRoute } from "vue-router";
import MaterialDownloadAction from "../components/MaterialDownloadAction.vue";
import SiteHeader from "../components/SiteHeader.vue";
import { api } from "../api.js";
import { publicUrl } from "../lib/publicUrl.js";

const route = useRoute();
const material = ref(null);
const loading = ref(true);
const error = ref("");
const materialId = computed(() => String(route.params.id || ""));
const fromMaterials = computed(() => route.query.from === "materials");
const returnName = computed(() => (fromMaterials.value ? "materials" : "search"));
const caseId = computed(() => String(route.query.caseId || ""));
const sourceUrl = computed(() => publicUrl(material.value?.sourceUrl));
const returnQuery = computed(() => queryForReturn(route.query, fromMaterials.value));
const returnLocation = computed(() => ({ name: returnName.value, query: returnQuery.value }));

const accessLabels = { public: "公开访问", campus: "校内访问", private: "私密访问" };
const authorityLabels = {
  original: "原始权威来源", secondary: "可靠二手来源", pending: "待核验线索",
};

function queryForReturn(query, materials) {
  const names = materials
    ? ["caseId", "q", "authority", "materialType", "accessLevel", "view"]
    : ["q", "kind", "view", "typeName", "audience", "authority", "materialType", "tag", "publishedWithin"];
  return Object.fromEntries(names.filter(name => query[name] != null).map(name => [name, query[name]]));
}

async function loadMaterial() {
  loading.value = true;
  error.value = "";
  try { material.value = await api.getMaterial(materialId.value); }
  catch (caught) { error.value = caught.message || "素材加载失败"; }
  finally { loading.value = false; }
}

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "未记录";
}

function accessLabel(value) {
  return accessLabels[value] || value || "未设置";
}

function authorityLabel(value) {
  return authorityLabels[value] || value || "未设置";
}

watch(materialId, loadMaterial, { immediate: true });
</script>

<template>
  <div class="home-page material-detail-page">
    <SiteHeader />
    <main id="main-content" class="material-detail-shell">
      <RouterLink class="material-detail-back" :to="returnLocation">
        <ArrowLeft :size="16" aria-hidden="true" />{{ fromMaterials ? "返回素材掌控台" : "返回资源检索" }}
      </RouterLink>
      <div v-if="loading" class="material-detail-state"><LoaderCircle class="spin" :size="22" />正在加载素材</div>
      <div v-else-if="error" class="material-detail-state error-state" role="alert">
        <AlertTriangle :size="22" /><span>{{ error }}</span>
        <button type="button" @click="loadMaterial"><RefreshCw :size="15" />重试</button>
      </div>
      <article v-else class="material-detail-content">
        <header class="material-detail-heading">
          <div><span class="home-eyebrow">素材详情</span><h1>{{ material.title }}</h1><p>{{ material.materialType || "未分类素材" }} · {{ authorityLabel(material.authority) }}</p></div>
          <div class="material-detail-actions">
            <MaterialDownloadAction :material="material" />
            <a v-if="sourceUrl" class="material-source-link" :href="sourceUrl" target="_blank" rel="noopener noreferrer"><ExternalLink :size="15" />查看原始网页</a>
          </div>
        </header>
        <div class="material-detail-layout">
          <section class="material-detail-main" aria-label="素材内容">
            <section v-if="material.summary" class="material-detail-summary">
              <h2>摘要</h2><p>{{ material.summary }}</p>
            </section>
            <section v-if="material.excerpt" class="material-detail-excerpt">
              <h2><FileText :size="17" />内容摘录</h2><p>{{ material.excerpt }}</p>
            </section>
            <p v-if="!material.summary && !material.excerpt" class="material-detail-empty">暂无可展示的内容摘录</p>
          </section>
          <aside class="material-detail-info">
            <h2>素材信息</h2>
            <dl>
              <dt>来源</dt><dd>{{ material.source || "未记录" }}</dd>
              <dt>素材类型</dt><dd>{{ material.materialType || "未分类" }}</dd>
              <dt>权威性</dt><dd>{{ authorityLabel(material.authority) }}</dd>
              <dt>访问范围</dt><dd>{{ accessLabel(material.accessLevel) }}</dd>
              <dt>内容状态</dt><dd>{{ material.contentAvailable ? "可查看" : "不可查看" }}</dd>
              <dt v-if="material.hasFile">文件</dt><dd v-if="material.hasFile">{{ material.filename || "原始文件" }}<span v-if="material.size"> · {{ material.size }} bytes</span></dd>
              <dt>采集时间</dt><dd>{{ dateLabel(material.collectedAt) }}</dd>
              <dt>发布时间</dt><dd>{{ dateLabel(material.publishedAt) }}</dd>
              <dt>更新时间</dt><dd>{{ dateLabel(material.updatedAt || material.createdAt) }}</dd>
              <dt v-if="material.citedCount != null">被引用</dt><dd v-if="material.citedCount != null">{{ material.citedCount }} 次</dd>
            </dl>
            <ul v-if="material.tags?.length" class="material-detail-tags"><li v-for="tag in material.tags" :key="tag">{{ tag }}</li></ul>
            <p v-if="!material.downloadAvailable" class="material-detail-note"><CalendarDays :size="14" />当前素材没有可下载文件</p>
          </aside>
        </div>
      </article>
    </main>
  </div>
</template>
