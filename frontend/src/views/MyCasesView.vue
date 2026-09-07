<script setup>
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, FilePlus2, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import CaseCard from "../components/CaseCard.vue";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const router = useRouter();
const cases = ref([]);
const loading = ref(true);
const creating = ref(false);
const error = ref("");
const groups = [
  { title: "退回修改", returned: true },
  { title: "进行中", statuses: ["draft"] },
  { title: "审核中", statuses: ["pending", "reviewing"] },
  { title: "已发布", statuses: ["published"] },
];
const statusLabels = { draft: "草稿", pending: "待审", reviewing: "审核中", published: "已发布" };
const actionLabels = {
  draft: "继续编辑",
  pending: "查看提交",
  reviewing: "查看审核",
  published: "查看公开页",
};

function isReturned(item) {
  return item.workflowStatus === "draft" && Boolean(item.lastReview);
}

function returnReason(item) {
  const review = item.lastReview;
  if (!review) return "";
  return `${review.reasonType}${review.summary ? `：${review.summary}` : ""}`;
}

function inGroup(group, item) {
  if (group.returned) return isReturned(item);
  return group.statuses.includes(item.workflowStatus) && !isReturned(item);
}

const groupedCases = computed(() => groups.map((group) => ({
  ...group,
  cases: cases.value.filter((item) => inGroup(group, item)),
})));
const returnedCases = computed(() => cases.value.filter(isReturned));

function caseDestination(item) {
  const publiclyReadable = item.workflowStatus === "published"
    && item.publicationStatus === "public";
  const name = publiclyReadable ? "case-public" : "workbench";
  return { name, params: { id: item.id } };
}

function cardStatus(item) {
  if (isReturned(item)) return "退回修改";
  if (item.publicationStatus === "hidden") return "已隐藏";
  const base = statusLabels[item.workflowStatus] || "未知状态";
  return item.publicationStatus === "public" && item.workflowStatus !== "published"
    ? `${base} · 旧版公开中` : base;
}

function cardAction(item) {
  if (isReturned(item)) return "处理退回意见";
  return item.publicationStatus === "hidden" ? "继续处理" : actionLabels[item.workflowStatus];
}

async function loadCases() {
  loading.value = true;
  error.value = "";
  try {
    cases.value = await api.listCases("mine");
    if (cases.value.some((item) => !Object.hasOwn(statusLabels, item.workflowStatus))) {
      throw new Error("部分案例状态异常，请重新加载。");
    }
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

      <div v-if="loading" class="catalog-state"><LoaderCircle class="spin" :size="22" /><span>正在加载案例</span></div>
      <div v-else-if="error" class="catalog-state error-state" role="alert">
        <AlertTriangle :size="22" /><span>{{ error }}</span>
        <button type="button" @click="loadCases"><RefreshCw :size="15" />重试</button>
      </div>
      <div v-else class="my-case-groups">
        <section
          v-if="returnedCases.length"
          class="my-case-group return-todo"
          aria-label="退回待办"
        >
          <header><h2>退回待办</h2><span>{{ returnedCases.length }}</span></header>
          <ul class="return-todo-list">
            <li v-for="item in returnedCases" :key="item.id">
              <RouterLink :to="caseDestination(item)"><b>{{ item.title }}</b></RouterLink>
              <span>{{ returnReason(item) }}</span>
              <em v-if="item.pendingAnnotationCount">待处理批注 {{ item.pendingAnnotationCount }} 条</em>
            </li>
          </ul>
        </section>
        <section v-for="group in groupedCases" :key="group.title" class="my-case-group">
          <header><h2>{{ group.title }}</h2><span>{{ group.cases.length }}</span></header>
          <div v-if="group.cases.length" class="case-grid">
            <CaseCard
              v-for="item in group.cases"
              :key="item.id"
              :case-record="item"
              :destination="caseDestination(item)"
              :status="cardStatus(item)"
              :action-label="cardAction(item)"
              :notice="returnReason(item)"
            />
          </div>
          <div v-else class="catalog-empty">暂无案例</div>
        </section>
      </div>
    </main>
  </div>
</template>
