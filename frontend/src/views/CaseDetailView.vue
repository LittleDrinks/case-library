<script setup>
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, Download, FilePenLine, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRoute } from "vue-router";
import PublishedDocument from "../components/PublishedDocument.vue";
import PublicAttachmentList from "../components/PublicAttachmentList.vue";
import PublicMaterialList from "../components/PublicMaterialList.vue";
import SiteHeader from "../components/SiteHeader.vue";
import { api } from "../api.js";
import { documentOutline, normalizeDocument } from "../lib/document.js";
import { session } from "../session.js";

const route = useRoute();
const caseId = String(route.params.id);
const caseRecord = ref(null);
const loading = ref(true);
const error = ref("");
const canOpenWorkbench = ref(false);
const outline = computed(() => documentOutline(caseRecord.value?.document));
const exportUrl = computed(() => `/api/cases/${encodeURIComponent(caseId)}/public/export.docx`);

async function loadCase() {
  loading.value = true;
  error.value = "";
  try {
    const value = await api.getPublicCase(caseId);
    caseRecord.value = { ...value, document: normalizeDocument(value.document) };
  } catch (reason) {
    error.value = reason.message || "案例加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadAccess() {
  if (!session.user) return;
  const mine = await api.listCases("mine");
  canOpenWorkbench.value = mine.some((item) => item.id === caseId);
}

async function initialize() {
  await Promise.all([loadCase(), loadAccess()]);
}

function locateHeading(order) {
  window.document.querySelectorAll(".published-document h1, .published-document h2")[order]
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function dateLabel(value) {
  return value ? String(value).slice(0, 10) : "未设置";
}

onMounted(initialize);
</script>

<template>
  <div class="case-detail-page">
    <SiteHeader />
    <main id="main-content" class="case-detail-main">
      <div v-if="loading" class="case-detail-state"><LoaderCircle class="spin" :size="22" />正在加载案例</div>
      <div v-else-if="error" class="case-detail-state error-state" role="alert">
        <AlertTriangle :size="22" />{{ error }}
        <button type="button" @click="loadCase"><RefreshCw :size="15" />重试</button>
      </div>
      <template v-else>
        <header class="case-detail-heading">
          <span>公开案例库</span>
          <h1>{{ caseRecord.title }}</h1>
          <p>{{ caseRecord.course || "课程未设置" }} · {{ caseRecord.typeName || "教学案例" }}</p>
        </header>
        <div class="case-detail-layout">
          <aside class="case-detail-outline" aria-label="内容目录">
            <h2>内容目录</h2>
            <button v-for="(item, order) in outline" :key="item.index" type="button" :class="`level-${item.level}`" @click="locateHeading(order)">{{ item.text }}</button>
            <p v-if="!outline.length">暂无目录</p>
          </aside>
          <article class="case-detail-paper">
            <section v-if="caseRecord.summary" class="case-detail-summary">
              <h2>案例摘要</h2>
              <p>{{ caseRecord.summary }}</p>
            </section>
            <PublishedDocument :document="caseRecord.document" />
          </article>
          <aside class="case-detail-info">
            <h2>案例信息</h2>
            <dl>
              <dt>案例类型</dt><dd>{{ caseRecord.typeName || "教学案例" }}</dd>
              <dt>适用学段</dt><dd>{{ caseRecord.stageText || "全部学段" }}</dd>
              <dt>作者</dt><dd>{{ caseRecord.author || "未设置" }}</dd>
              <dt>单位</dt><dd>{{ caseRecord.organization || "未设置" }}</dd>
              <dt>发布日期</dt><dd>{{ dateLabel(caseRecord.publishedAt) }}</dd>
            </dl>
            <ul v-if="caseRecord.theoryPoints?.length" class="case-detail-tags">
              <li v-for="point in caseRecord.theoryPoints" :key="point">{{ point }}</li>
            </ul>
            <PublicAttachmentList :case-id="caseId" :version-id="caseRecord.publishedVersionId" :is-owner="canOpenWorkbench" />
            <PublicMaterialList :case-id="caseId" :version-id="caseRecord.publishedVersionId" />
            <RouterLink v-if="canOpenWorkbench" class="case-detail-workbench" :to="{ name: 'workbench', params: { id: caseId } }"><FilePenLine :size="16" aria-hidden="true" />进入工作台</RouterLink>
            <a class="case-detail-export" :href="exportUrl" download><Download :size="16" aria-hidden="true" />导出 DOCX</a>
          </aside>
        </div>
      </template>
    </main>
  </div>
</template>
