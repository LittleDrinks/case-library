<script setup>
import { ChevronLeft, ChevronRight, KeyRound, LoaderCircle, LogOut, RefreshCw, Search, Users, UserPlus, X } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { api, formatApiError } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const activeTab = ref("accounts");
const query = ref("");
const searchQuery = ref("");
const accounts = ref({ items: [], total: 0, page: 1, pageSize: 25 });
const operations = ref({ items: [], total: 0, page: 1, pageSize: 25 });
const loading = ref(false);
const error = ref("");
const actionError = ref("");
const notice = ref("");
const saving = ref(false);
const operationTarget = ref(null);
const openForm = reactive({ username: "", temporaryPassword: "", reason: "" });
const actionForm = reactive({ temporaryPassword: "", reason: "" });
const activePage = computed(() => activeTab.value === "accounts" ? accounts.value : operations.value);
const totalPages = computed(() => Math.max(1, Math.ceil(activePage.value.total / activePage.value.pageSize)));

function publicError(reason, fallback) {
  return formatApiError(reason, fallback);
}

function requiredTextError(value, label, maxLength) {
  const text = value.trim();
  if (!text) return `${label}不能为空`;
  if (text.length > maxLength) return `${label}不能超过 ${maxLength} 个字符`;
  return "";
}

async function loadAccounts(page = 1) {
  loading.value = true;
  error.value = "";
  try {
    accounts.value = await api.listManagedAccounts(searchQuery.value, page);
  } catch (reason) {
    error.value = publicError(reason, "账号列表加载失败");
  } finally {
    loading.value = false;
  }
}

async function loadOperations(page = 1) {
  loading.value = true;
  error.value = "";
  try {
    operations.value = await api.listAccountOperations(page);
  } catch (reason) {
    error.value = publicError(reason, "操作记录加载失败");
  } finally {
    loading.value = false;
  }
}

async function search() {
  searchQuery.value = query.value.trim();
  await loadAccounts();
}

async function selectTab(tab) {
  activeTab.value = tab;
  operationTarget.value = null;
  actionError.value = "";
  if (tab === "accounts") await loadAccounts(accounts.value.page);
  else await loadOperations(operations.value.page);
}

async function openAccount() {
  actionError.value = "";
  notice.value = "";
  const inputError = requiredTextError(openForm.username, "用户名", 80)
    || requiredTextError(openForm.reason, "操作理由", 500);
  if (inputError) {
    actionError.value = inputError;
    return;
  }
  saving.value = true;
  try {
    const account = await api.openManagedAccount({
      username: openForm.username.trim(),
      temporaryPassword: openForm.temporaryPassword,
      reason: openForm.reason.trim(),
    }, session.csrfToken);
    notice.value = `已为 ${account.username} 开户`;
    openForm.username = "";
    openForm.temporaryPassword = "";
    openForm.reason = "";
    await loadAccounts(1);
  } catch (reason) {
    actionError.value = publicError(reason, "开户失败");
  } finally {
    saving.value = false;
  }
}

function beginAction(account, kind) {
  operationTarget.value = { account, kind };
  actionForm.temporaryPassword = "";
  actionForm.reason = "";
  actionError.value = "";
  notice.value = "";
}

function cancelAction() {
  operationTarget.value = null;
  actionForm.temporaryPassword = "";
  actionForm.reason = "";
  actionError.value = "";
}

async function submitAction() {
  if (!operationTarget.value || saving.value) return;
  const { account, kind } = operationTarget.value;
  actionError.value = "";
  notice.value = "";
  const inputError = requiredTextError(actionForm.reason, "操作理由", 500);
  if (inputError) {
    actionError.value = inputError;
    return;
  }
  saving.value = true;
  try {
    if (kind === "reset") {
      await api.resetManagedAccountPassword(account.id, {
        temporaryPassword: actionForm.temporaryPassword,
        reason: actionForm.reason.trim(),
      }, session.csrfToken);
      notice.value = `已为 ${account.username} 设置新的临时密码`;
    } else {
      const result = await api.forceLogoutManagedAccount(account.id, {
        reason: actionForm.reason.trim(),
      }, session.csrfToken);
      notice.value = `已强制退出 ${account.username}，撤销 ${result.revokedSessions} 个会话`;
    }
    cancelAction();
    await loadAccounts(accounts.value.page);
  } catch (reason) {
    actionError.value = publicError(reason, kind === "reset" ? "密码重置失败" : "强制退出失败");
  } finally {
    saving.value = false;
  }
}

function changePage(delta) {
  const next = activePage.value.page + delta;
  if (next < 1 || next > totalPages.value) return;
  if (activeTab.value === "accounts") void loadAccounts(next);
  else void loadOperations(next);
}

function actionLabel(action) {
  return {
    account_open: "后台开户",
    temporary_password_reset: "重置临时密码",
    force_logout: "强制退出",
  }[action] || action;
}

function dateLabel(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "时间未知";
}

onMounted(() => loadAccounts());
</script>

<template>
  <div class="admin-page">
    <SiteHeader />
    <main id="main-content" class="admin-main account-admin-main">
      <header class="admin-heading account-admin-heading">
        <div><span>平台管理</span><h1>账号管理</h1></div>
        <nav aria-label="管理工具">
          <RouterLink :to="{ name: 'admin-dashboard' }"><Users :size="16" />管理后台</RouterLink>
        </nav>
      </header>

      <div class="account-tabs" role="tablist" aria-label="账号管理视图">
        <button type="button" role="tab" :aria-selected="activeTab === 'accounts'" @click="selectTab('accounts')">
          <Users :size="16" aria-hidden="true" />账号
        </button>
        <button type="button" role="tab" :aria-selected="activeTab === 'operations'" @click="selectTab('operations')">
          <LogOut :size="16" aria-hidden="true" />操作记录
        </button>
      </div>

      <template v-if="activeTab === 'accounts'">
        <section class="account-open" aria-labelledby="account-open-title">
          <header><UserPlus :size="18" aria-hidden="true" /><h2 id="account-open-title">开立普通账号</h2></header>
          <form class="account-open-form" @submit.prevent="openAccount">
            <label><span>用户名</span><input v-model="openForm.username" autocomplete="off" maxlength="80" required /></label>
            <label><span>临时密码</span><input v-model="openForm.temporaryPassword" type="password" autocomplete="new-password" maxlength="128" required /></label>
            <label class="account-reason-field"><span>操作理由</span><input v-model="openForm.reason" maxlength="500" required /></label>
            <button class="account-primary-button" type="submit" :disabled="saving">
              <LoaderCircle v-if="saving" class="spin" :size="16" aria-hidden="true" />
              <UserPlus v-else :size="16" aria-hidden="true" />
              <span>{{ saving ? "正在开户" : "开户" }}</span>
            </button>
          </form>
        </section>

        <form class="account-search" role="search" @submit.prevent="search">
          <label for="account-search-input">搜索用户名</label>
          <input id="account-search-input" v-model="query" maxlength="80" />
          <button type="submit" title="搜索账号" aria-label="搜索账号"><Search :size="17" aria-hidden="true" /></button>
          <button type="button" title="刷新账号" aria-label="刷新账号" @click="loadAccounts(accounts.page)"><RefreshCw :size="16" aria-hidden="true" /></button>
        </form>
      </template>

      <div v-if="notice" class="account-notice" role="status">{{ notice }}</div>
      <div v-if="actionError" class="account-error" role="alert">{{ actionError }}</div>

      <section v-if="operationTarget" class="account-action" aria-labelledby="account-action-title">
        <header>
          <h2 id="account-action-title">
            {{ operationTarget.kind === "reset" ? "重置临时密码" : "强制退出" }}：{{ operationTarget.account.username }}
          </h2>
          <button type="button" class="account-icon-button" title="取消操作" aria-label="取消操作" @click="cancelAction"><X :size="17" aria-hidden="true" /></button>
        </header>
        <form class="account-action-form" @submit.prevent="submitAction">
          <label v-if="operationTarget.kind === 'reset'">
            <span>新临时密码</span>
            <input v-model="actionForm.temporaryPassword" type="password" autocomplete="new-password" maxlength="128" required />
          </label>
          <label><span>操作理由</span><input v-model="actionForm.reason" maxlength="500" required /></label>
          <div class="account-action-buttons">
            <button class="account-primary-button" type="submit" :disabled="saving">
              <LoaderCircle v-if="saving" class="spin" :size="16" aria-hidden="true" />
              <KeyRound v-else-if="operationTarget.kind === 'reset'" :size="16" aria-hidden="true" />
              <LogOut v-else :size="16" aria-hidden="true" />
              <span>{{ saving ? "正在处理" : "确认" }}</span>
            </button>
            <button class="account-secondary-button" type="button" :disabled="saving" @click="cancelAction">取消</button>
          </div>
        </form>
      </section>

      <div v-if="loading" class="admin-state"><LoaderCircle class="spin" :size="20" aria-hidden="true" />正在加载</div>
      <div v-else-if="error" class="admin-state error-state" role="alert">
        {{ error }}<button type="button" @click="activeTab === 'accounts' ? loadAccounts(accounts.page) : loadOperations(operations.page)"><RefreshCw :size="15" aria-hidden="true" />重试</button>
      </div>
      <template v-else-if="activeTab === 'accounts'">
        <section class="account-results" aria-label="账号列表" aria-live="polite">
          <div v-if="!accounts.items.length" class="admin-empty">没有匹配的账号</div>
          <article v-for="account in accounts.items" :key="account.id" class="account-row">
            <div class="account-identity">
              <h2>{{ account.username }}</h2>
              <p>{{ account.role === "admin" ? "管理员" : "普通用户" }}<span v-if="account.mustChangePassword"> · 首次登录需改密</span></p>
            </div>
            <div class="account-row-actions">
              <button type="button" class="account-secondary-button" @click="beginAction(account, 'reset')"><KeyRound :size="15" aria-hidden="true" />重置临时密码</button>
              <button type="button" class="account-secondary-button" @click="beginAction(account, 'logout')"><LogOut :size="15" aria-hidden="true" />强制退出</button>
            </div>
          </article>
        </section>
        <nav v-if="accounts.total" class="account-pagination" aria-label="账号分页">
          <span>共 {{ accounts.total }} 个账号</span>
          <button type="button" title="上一页" aria-label="上一页" :disabled="accounts.page <= 1 || loading" @click="changePage(-1)"><ChevronLeft :size="17" /></button>
          <span>第 {{ accounts.page }} / {{ totalPages }} 页</span>
          <button type="button" title="下一页" aria-label="下一页" :disabled="accounts.page >= totalPages || loading" @click="changePage(1)"><ChevronRight :size="17" /></button>
        </nav>
      </template>
      <template v-else>
        <section class="account-operation-list" aria-label="账号操作记录" aria-live="polite">
          <div v-if="!operations.items.length" class="admin-empty">暂无操作记录</div>
          <article v-for="operation in operations.items" :key="operation.id" class="account-operation-row">
            <header><strong>{{ actionLabel(operation.action) }}</strong><span :data-result="operation.result">{{ operation.result === "success" ? "成功" : "已拒绝" }}</span><time :datetime="operation.createdAt">{{ dateLabel(operation.createdAt) }}</time></header>
            <p><b>{{ operation.actorUsername }}</b> → {{ operation.targetUsername || "未知账号" }} · {{ operation.detail }}</p>
            <p class="account-operation-reason">理由：{{ operation.reason }}</p>
          </article>
        </section>
        <nav v-if="operations.total" class="account-pagination" aria-label="操作记录分页">
          <span>共 {{ operations.total }} 条记录</span>
          <button type="button" title="上一页" aria-label="上一页" :disabled="operations.page <= 1 || loading" @click="changePage(-1)"><ChevronLeft :size="17" /></button>
          <span>第 {{ operations.page }} / {{ totalPages }} 页</span>
          <button type="button" title="下一页" aria-label="下一页" :disabled="operations.page >= totalPages || loading" @click="changePage(1)"><ChevronRight :size="17" /></button>
        </nav>
      </template>
    </main>
  </div>
</template>
