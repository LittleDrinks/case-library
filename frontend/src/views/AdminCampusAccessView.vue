<script setup>
import { Check, ChevronLeft, ChevronRight, GraduationCap, LoaderCircle, RefreshCw, Search, ShieldOff, X } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { api, formatApiError } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const queue = ref({ items: [], total: 0, page: 1, pageSize: 50 });
const legacyGrants = ref({ items: [], total: 0, page: 1, pageSize: 50 });
const filter = reactive({ query: "", status: "pending" });
const loading = ref(true);
const legacyLoading = ref(true);
const legacyError = ref("");
const saving = ref(false);
const error = ref("");
const actionError = ref("");
const notice = ref("");
const action = ref(null);
const reason = ref("");

const totalPages = computed(() => Math.max(1, Math.ceil(queue.value.total / queue.value.pageSize)));
const legacyTotalPages = computed(() => Math.max(1, Math.ceil(legacyGrants.value.total / legacyGrants.value.pageSize)));
const statusLabels = {
  pending: "待审核",
  approved: "已批准",
  rejected: "已拒绝",
  revoked: "已撤销",
};

function eventLabel(name) {
  return {
    campus_access_application_submit: "提交申请",
    campus_access_approve: "批准申请",
    campus_access_reject: "拒绝申请",
    campus_access_revoke: "撤销资格",
  }[name] || name;
}

function dateLabel(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "时间未知";
}

async function loadApplications(page = 1) {
  loading.value = true;
  error.value = "";
  try {
    queue.value = await api.listCampusAccessApplications(
      filter.query.trim(), filter.status, page, queue.value.pageSize,
    );
  } catch (reasonValue) {
    error.value = formatApiError(reasonValue, "校内申请列表加载失败");
  } finally {
    loading.value = false;
  }
}

async function loadLegacyGrants(page = legacyGrants.value.page) {
  legacyLoading.value = true;
  legacyError.value = "";
  try {
    const result = await api.listLegacyCampusGrants(
      filter.query.trim(), page, legacyGrants.value.pageSize,
    );
    const lastPage = Math.max(1, Math.ceil(result.total / result.pageSize));
    if (page > lastPage) {
      await loadLegacyGrants(lastPage);
      return;
    }
    legacyGrants.value = result;
  } catch (reasonValue) {
    legacyError.value = formatApiError(reasonValue, "旧系统授权列表加载失败");
  } finally {
    legacyLoading.value = false;
  }
}

function beginAction(application, kind) {
  action.value = { application, kind };
  reason.value = "";
  actionError.value = "";
  notice.value = "";
}

function cancelAction() {
  action.value = null;
  reason.value = "";
  actionError.value = "";
}

function beginLegacyRevoke(grant) {
  action.value = { grant, kind: "revokeLegacy" };
  reason.value = "";
  actionError.value = "";
  notice.value = "";
}

async function submitAction() {
  if (!action.value || saving.value) return;
  const detail = reason.value.trim();
  if (!detail) {
    actionError.value = "操作理由不能为空";
    return;
  }
  if (detail.length > 500) {
    actionError.value = "操作理由不能超过 500 个字符";
    return;
  }
  const { application, grant, kind } = action.value;
  saving.value = true;
  actionError.value = "";
  try {
    if (kind === "revokeLegacy") {
      await api.revokeLegacyCampusGrant(grant.userId, detail, session.csrfToken);
      notice.value = `已撤销 ${grant.username} 的旧系统校内资格`;
    } else if (kind === "revoke") {
      await api.revokeCampusAccessApplication(application.id, detail, session.csrfToken);
      notice.value = `已撤销 ${application.username} 的校内资格`;
    } else {
      await api.decideCampusAccessApplication(
        application.id, kind === "approve" ? "approved" : "rejected", detail, session.csrfToken,
      );
      notice.value = kind === "approve" ? `已批准 ${application.username}` : `已拒绝 ${application.username}`;
    }
    cancelAction();
    await Promise.all([
      loadApplications(queue.value.page),
      loadLegacyGrants(legacyGrants.value.page),
    ]);
  } catch (reasonValue) {
    actionError.value = formatApiError(reasonValue, "校内申请处理失败");
  } finally {
    saving.value = false;
  }
}

function changePage(delta) {
  const next = queue.value.page + delta;
  if (next < 1 || next > totalPages.value) return;
  void loadApplications(next);
}

function changeLegacyPage(delta) {
  const next = legacyGrants.value.page + delta;
  if (next < 1 || next > legacyTotalPages.value) return;
  void loadLegacyGrants(next);
}

function searchCampusAccess() {
  void Promise.all([loadApplications(1), loadLegacyGrants(1)]);
}

function refreshCampusAccessLists() {
  void Promise.all([
    loadApplications(queue.value.page),
    loadLegacyGrants(legacyGrants.value.page),
  ]);
}

onMounted(() => {
  void loadApplications();
  void loadLegacyGrants();
});
</script>

<template>
  <div class="admin-page campus-admin-page">
    <SiteHeader />
    <main id="main-content" class="admin-main campus-admin-main">
      <header class="admin-heading campus-admin-heading">
        <div><span>账号管理</span><h1>校内访问申请</h1></div>
        <nav aria-label="管理工具">
          <RouterLink :to="{ name: 'admin-dashboard' }">管理后台</RouterLink>
          <RouterLink :to="{ name: 'admin-accounts' }">账号管理</RouterLink>
        </nav>
      </header>

      <form class="campus-admin-filters" role="search" @submit.prevent="searchCampusAccess">
        <label><span>搜索申请人</span><input v-model="filter.query" maxlength="80" /></label>
        <label><span>申请状态</span>
          <select v-model="filter.status">
            <option value="pending">待审核</option>
            <option value="approved">已批准</option>
            <option value="rejected">已拒绝</option>
            <option value="revoked">已撤销</option>
            <option value="all">全部记录</option>
          </select>
        </label>
        <button type="submit" :disabled="loading || legacyLoading"><Search :size="16" aria-hidden="true" />查询</button>
        <button type="button" class="campus-admin-refresh" title="刷新申请与旧系统授权" aria-label="刷新申请与旧系统授权" :disabled="loading || legacyLoading" @click="refreshCampusAccessLists"><RefreshCw :size="16" aria-hidden="true" /></button>
      </form>

      <p v-if="notice" class="campus-access-notice" role="status">{{ notice }}</p>
      <section v-if="action" class="campus-admin-action" aria-labelledby="campus-admin-action-title">
        <header>
          <div><span>{{ action.grant?.username || action.application.username }}</span><h2 id="campus-admin-action-title">{{ action.kind === "approve" ? "批准申请" : action.kind === "reject" ? "拒绝申请" : action.kind === "revokeLegacy" ? "撤销旧系统授权" : "撤销校内资格" }}</h2></div>
          <button type="button" class="campus-admin-icon-button" title="取消操作" aria-label="取消操作" @click="cancelAction"><X :size="17" aria-hidden="true" /></button>
        </header>
        <p v-if="action.grant">旧系统授权 · 无历史申请或自填身份资料</p>
        <p v-else>{{ action.application.applicantName }} · {{ action.application.studentNumber }}</p>
        <form @submit.prevent="submitAction">
          <label for="campus-admin-reason">操作理由</label>
          <textarea id="campus-admin-reason" v-model="reason" maxlength="500" required rows="3" />
          <p v-if="actionError" class="campus-access-error" role="alert">{{ actionError }}</p>
          <footer>
            <button type="submit" class="campus-admin-confirm" :disabled="saving">
              <LoaderCircle v-if="saving" class="spin" :size="16" aria-hidden="true" />
              <Check v-else-if="action.kind === 'approve'" :size="16" aria-hidden="true" />
              <ShieldOff v-else-if="action.kind === 'revoke' || action.kind === 'revokeLegacy'" :size="16" aria-hidden="true" />
              <X v-else :size="16" aria-hidden="true" />
              {{ saving ? "正在保存" : action.kind === "approve" ? "确认批准" : action.kind === "reject" ? "确认拒绝" : "确认撤销" }}
            </button>
            <button type="button" class="campus-admin-cancel" :disabled="saving" @click="cancelAction">取消</button>
          </footer>
        </form>
      </section>

      <div v-if="loading" class="admin-state"><LoaderCircle class="spin" :size="20" aria-hidden="true" />正在加载申请</div>
      <div v-else-if="error" class="admin-state error-state" role="alert">{{ error }}<button type="button" @click="loadApplications(queue.page)"><RefreshCw :size="15" aria-hidden="true" />重试</button></div>
      <section v-else class="campus-admin-results" aria-label="校内访问申请列表" aria-live="polite">
        <p v-if="!queue.items.length" class="campus-access-empty">没有匹配的申请记录</p>
        <article v-for="application in queue.items" :key="application.id" class="campus-admin-row">
          <header>
            <div class="campus-admin-applicant"><span>{{ application.username }}</span><strong>{{ application.applicantName }}</strong><code>{{ application.studentNumber }}</code></div>
            <div class="campus-admin-row-state"><span :data-status="application.status">{{ statusLabels[application.status] }}</span><time :datetime="application.submittedAt">{{ dateLabel(application.submittedAt) }}</time></div>
          </header>
          <p class="campus-admin-source">本人填报 · 申请记录 {{ application.id }}</p>
          <ol v-if="application.history.length" class="campus-application-events">
            <li v-for="event in application.history" :key="event.id">
              <span>{{ eventLabel(event.action) }} · {{ event.detail }}</span>
              <time :datetime="event.createdAt">{{ dateLabel(event.createdAt) }} · {{ event.actorUsername }}</time>
              <p v-if="event.reason">理由：{{ event.reason }}</p>
            </li>
          </ol>
          <footer v-if="application.status === 'pending' || application.status === 'approved'">
            <button v-if="application.status === 'pending'" type="button" class="campus-admin-approve" @click="beginAction(application, 'approve')"><Check :size="15" aria-hidden="true" />批准</button>
            <button v-if="application.status === 'pending'" type="button" class="campus-admin-reject" @click="beginAction(application, 'reject')"><X :size="15" aria-hidden="true" />拒绝</button>
            <button v-else type="button" class="campus-admin-reject" @click="beginAction(application, 'revoke')"><ShieldOff :size="15" aria-hidden="true" />撤销资格</button>
          </footer>
        </article>
      </section>
      <section class="campus-admin-legacy" aria-labelledby="campus-admin-legacy-title">
        <header><div><span>来源单独标记，不创建历史申请</span><h2 id="campus-admin-legacy-title">旧系统授权</h2></div><span>共 {{ legacyGrants.total }} 个账号</span></header>
        <div v-if="legacyLoading" class="admin-state"><LoaderCircle class="spin" :size="18" aria-hidden="true" />正在加载旧系统授权</div>
        <div v-else-if="legacyError" class="admin-state error-state" role="alert">{{ legacyError }}<button type="button" @click="loadLegacyGrants()"><RefreshCw :size="15" aria-hidden="true" />重试</button></div>
        <p v-else-if="!legacyGrants.items.length" class="campus-access-empty">没有匹配的旧系统授权</p>
        <article v-for="grant in legacyGrants.items" :key="grant.userId" class="campus-admin-row">
          <header>
            <div class="campus-admin-applicant"><span>{{ grant.username }}</span><strong>{{ grant.role === "admin" ? "管理员" : "普通用户" }}</strong></div>
            <div class="campus-admin-row-state"><span data-status="approved">旧系统授权</span></div>
          </header>
          <p class="campus-admin-source">账号 {{ grant.userId }} · 当前校内资格来自旧系统显式授权</p>
          <footer><button type="button" class="campus-admin-reject" @click="beginLegacyRevoke(grant)"><ShieldOff :size="15" aria-hidden="true" />撤销资格</button></footer>
        </article>
        <nav v-if="legacyGrants.total" class="account-pagination" aria-label="旧系统授权分页">
          <span>共 {{ legacyGrants.total }} 个账号</span>
          <button type="button" title="上一页旧系统授权" aria-label="上一页旧系统授权" :disabled="legacyGrants.page <= 1 || legacyLoading" @click="changeLegacyPage(-1)"><ChevronLeft :size="17" /></button>
          <span>第 {{ legacyGrants.page }} / {{ legacyTotalPages }} 页</span>
          <button type="button" title="下一页旧系统授权" aria-label="下一页旧系统授权" :disabled="legacyGrants.page >= legacyTotalPages || legacyLoading" @click="changeLegacyPage(1)"><ChevronRight :size="17" /></button>
        </nav>
      </section>
      <nav v-if="queue.total" class="account-pagination" aria-label="申请记录分页">
        <span>共 {{ queue.total }} 条申请</span>
        <button type="button" title="上一页" aria-label="上一页" :disabled="queue.page <= 1 || loading" @click="changePage(-1)"><ChevronLeft :size="17" /></button>
        <span>第 {{ queue.page }} / {{ totalPages }} 页</span>
        <button type="button" title="下一页" aria-label="下一页" :disabled="queue.page >= totalPages || loading" @click="changePage(1)"><ChevronRight :size="17" /></button>
      </nav>
    </main>
  </div>
</template>
