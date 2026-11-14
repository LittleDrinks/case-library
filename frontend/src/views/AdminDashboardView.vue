<script setup>
import { FileStack, LoaderCircle, RefreshCw, Search } from "@lucide/vue";
import { reactive, ref } from "vue";
import { api } from "../api.js";
import AdminPagination from "../components/AdminPagination.vue";
import { useAdminPage } from "../composables/useAdminPage.js";
const query = ref("");
const queues = [
  { key: "review", title: "案例审核", state: reactive(useAdminPage(params => api.listAdminCases("review", params))) },
  { key: "published", title: "发布管理", state: reactive(useAdminPage(params => api.listAdminCases("published", params))) },
];
function search() { for (const queue of queues) queue.state.search(query.value.trim()); }
function dateLabel(value) { return value ? String(value).slice(0, 10) : "日期待定"; }
function statusLabel(item) { return item.workflowStatus === "pending" ? "待开始" : "审核中"; }
</script>
<template>
  <section class="admin-overview">
    <header class="admin-heading"><h1>管理后台</h1></header>
    <form class="admin-list-toolbar" role="search" aria-label="搜索管理案例" @submit.prevent="search">
      <input v-model="query" aria-label="案例标题" placeholder="搜索案例标题" maxlength="200" />
      <button class="secondary-button" type="submit"><Search :size="16" />搜索</button>
    </form>
    <section v-for="queue in queues" :key="queue.key" class="admin-queue" :aria-labelledby="`${queue.key}-queue-title`">
      <header><h2 :id="`${queue.key}-queue-title`">{{ queue.title }}</h2><b>{{ queue.state.total }}</b></header>
      <div v-if="queue.state.loading" class="admin-state"><LoaderCircle class="spin" :size="20" />正在加载管理队列</div>
      <div v-else-if="queue.state.error" class="admin-state error-state" role="alert">
        {{ queue.state.error }}<button type="button" @click="queue.state.reload"><RefreshCw :size="15" />重试</button>
      </div>
      <template v-else>
        <p v-if="!queue.state.items.length" class="admin-empty">{{ query ? "没有匹配的案例" : queue.key === "review" ? "暂无待审核案例" : "暂无已发布案例" }}</p>
        <article v-for="item in queue.state.items" :key="item.id" :aria-label="`${queue.key === 'review' ? '待审核' : '已发布'}：${item.title}`">
          <span v-if="queue.key === 'review'" :data-status="item.workflowStatus">{{ statusLabel(item) }}</span>
          <FileStack v-else :size="18" aria-hidden="true" />
          <div><h3>{{ item.title }}</h3><p v-if="queue.key === 'review'">{{ item.author || "作者待补充" }} · 提交更新 {{ dateLabel(item.updatedAt) }}</p>
            <p v-else>{{ item.publicationStatus === "public" ? "公开中" : "已隐藏" }} · {{ dateLabel(item.publishedAt) }}</p></div>
          <RouterLink :to="{ name: 'case-review', params: { id: item.id } }">{{ queue.key === "review" ? "审核" : "发布管理" }}</RouterLink>
        </article>
      </template>
      <AdminPagination :total="queue.state.total" :page="queue.state.page" :page-size="queue.state.pageSize"
                       :loading="queue.state.loading" :label="`${queue.title}分页`"
                       @page="queue.state.page = $event" @page-size="queue.state.resize" />
    </section>
  </section>
</template>
