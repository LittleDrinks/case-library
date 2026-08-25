<script setup>
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, FilePlus2, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api.js";
import CaseCard from "../components/CaseCard.vue";
import { caseUnavailableMessage, caseUnavailableNotice } from "../lib/workbenchAccess.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const route = useRoute();
const router = useRouter();
const cases = ref([]);
const loading = ref(true);
const creating = ref(false);
const error = ref("");
const accessNotice = computed(() => (
  route.query.notice === caseUnavailableNotice ? caseUnavailableMessage : ""
));
const groups = [
  { title: "进行中", statuses: ["draft"] },
  { title: "审核中", statuses: ["pending", "reviewing"] },
  { title: "已发布", statuses: ["published"] },
];
const statusLabels = { draft: "草稿", pending: "待审", reviewing: "审核中", published: "已发布" };
const actionLabels = {
  draft: "继续编辑",
  pending: "查看提交",
  reviewing: "查看审核",
  published: "打开工作台",
};
const groupedCases = computed(() => groups.map((group) => ({
  ...group,
  cases: cases.value.filter((item) => group.statuses.includes(item.workflowStatus)),
})));

function caseDestination(item) {
  return { name: "workbench", params: { id: item.id } };
}

async function loadCases() {
  loading.value = true;
  error.value = "";
  try {
    cases.value = await api.listCases("mine");
  } catch (reason) {
    error.value = reason.message || "案例加载失败";
  } finally {
    loading.value = false;
  }
}

async function createCase() {
  creating.value = true;
  error.value = "";
  try {
    const created = await api.createCase({ title: "未命名案例" }, session.csrfToken);
    await router.push({ name: "workbench", params: { id: created.id } });
  } catch (reason) {
    error.value = reason.message || "新建案例失败";
  } finally {
    creating.value = false;
  }
}

onMounted(loadCases);
</script>

<template>
  <div class="home-page">
    <SiteHeader />
    <main id="main-content" class="home-main my-cases-main">
      <header class="my-cases-heading">
        <div><span class="home-eyebrow">教学工作</span><h1>我的案例</h1></div>
        <button type="button" :disabled="creating" @click="createCase">
          <LoaderCircle v-if="creating" class="spin" :size="17" aria-hidden="true" />
          <FilePlus2 v-else :size="17" aria-hidden="true" />
          {{ creating ? "正在创建" : "新建案例" }}
        </button>
      </header>
      <p v-if="accessNotice" class="catalog-notice" role="alert">{{ accessNotice }}</p>

      <div v-if="loading" class="catalog-state"><LoaderCircle class="spin" :size="22" /><span>正在加载案例</span></div>
      <div v-else-if="error" class="catalog-state error-state" role="alert">
        <AlertTriangle :size="22" /><span>{{ error }}</span>
        <button type="button" @click="loadCases"><RefreshCw :size="15" />重试</button>
      </div>
      <div v-else class="my-case-groups">
        <section v-for="group in groupedCases" :key="group.title" class="my-case-group">
          <header><h2>{{ group.title }}</h2><span>{{ group.cases.length }}</span></header>
          <div v-if="group.cases.length" class="case-grid">
            <CaseCard
              v-for="item in group.cases"
              :key="item.id"
              :case-record="item"
              :destination="caseDestination(item)"
              :status="statusLabels[item.workflowStatus]"
              :action-label="actionLabels[item.workflowStatus]"
            />
          </div>
          <div v-else class="catalog-empty">暂无案例</div>
        </section>
      </div>
    </main>
  </div>
</template>
