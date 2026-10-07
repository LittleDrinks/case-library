<script setup>
import { CheckCircle2, Clock3, GraduationCap, LoaderCircle, Send } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";
import { api, formatApiError } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const status = ref({ campusVerified: false, currentStatus: "not_applied", applications: [] });
const form = reactive({ applicantName: "", studentNumber: "" });
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notice = ref("");

const canApply = computed(() => (
  !status.value.campusVerified
  && ["not_applied", "rejected", "revoked"].includes(status.value.currentStatus)
));

const statusLabels = {
  not_applied: "尚未申请",
  pending: "等待管理员审核",
  approved: "申请已批准",
  rejected: "申请被拒绝",
  revoked: "校内资格已撤销",
};

function statusMessage() {
  if (status.value.campusVerified) return "当前账号已获准访问校内来源。";
  if (status.value.currentStatus === "pending") return "当前仍无校内访问资格，审核通过后状态会更新。";
  if (status.value.currentStatus === "rejected") return "当前仍无校内访问资格，可以重新提交申请。";
  if (status.value.currentStatus === "revoked") return "当前校内访问资格已撤销，可以重新申请并等待人工批准。";
  return "校内资格与普通账号创作分开管理。";
}

function eventLabel(action) {
  return {
    campus_access_application_submit: "提交申请",
    campus_access_approve: "批准申请",
    campus_access_reject: "拒绝申请",
    campus_access_revoke: "撤销资格",
  }[action] || action;
}

function dateLabel(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "时间未知";
}

async function loadStatus() {
  loading.value = true;
  error.value = "";
  try {
    status.value = await api.campusAccessStatus();
  } catch (reason) {
    error.value = formatApiError(reason, "校内申请状态加载失败");
  } finally {
    loading.value = false;
  }
}

async function submitApplication() {
  if (saving.value) return;
  error.value = "";
  notice.value = "";
  const applicantName = form.applicantName.trim();
  const studentNumber = form.studentNumber.trim();
  if (!applicantName || !studentNumber) {
    error.value = "姓名和学工号均为必填项";
    return;
  }
  saving.value = true;
  try {
    await api.submitCampusAccessApplication({ applicantName, studentNumber }, session.csrfToken);
    form.applicantName = "";
    form.studentNumber = "";
    notice.value = "申请已提交";
    await loadStatus();
  } catch (reason) {
    error.value = formatApiError(reason, "校内访问申请提交失败");
  } finally {
    saving.value = false;
  }
}

onMounted(loadStatus);
</script>

<template>
  <div class="campus-access-page">
    <SiteHeader />
    <main id="main-content" class="admin-main campus-access-main">
      <header class="admin-heading">
        <div><span>账号授权</span><h1>校内访问</h1></div>
      </header>

      <div v-if="loading" class="admin-state"><LoaderCircle class="spin" :size="20" aria-hidden="true" />正在加载申请状态</div>
      <template v-else>
        <section class="campus-access-current" :data-status="status.currentStatus" aria-live="polite">
          <div class="campus-access-mark" aria-hidden="true">
            <CheckCircle2 v-if="status.campusVerified" :size="22" />
            <Clock3 v-else :size="22" />
          </div>
          <div>
            <p>当前资格</p>
            <h2>{{ status.campusVerified ? "已获校内访问资格" : statusLabels[status.currentStatus] }}</h2>
            <span>{{ statusMessage() }}</span>
          </div>
        </section>

        <p v-if="notice" class="campus-access-notice" role="status">{{ notice }}</p>
        <p v-if="error" class="campus-access-error" role="alert">{{ error }}</p>

        <section v-if="canApply" class="campus-access-application" aria-labelledby="campus-apply-title">
          <header><GraduationCap :size="18" aria-hidden="true" /><h2 id="campus-apply-title">提交校内访问申请</h2></header>
          <p>申请资料按本人填报信息保存，仅用于本次资格审核。</p>
          <form @submit.prevent="submitApplication">
            <label>
              <span>姓名</span>
              <input v-model="form.applicantName" name="applicantName" autocomplete="name" maxlength="120" required />
            </label>
            <label>
              <span>学工号</span>
              <input v-model="form.studentNumber" name="studentNumber" autocomplete="off" maxlength="80" required />
            </label>
            <button type="submit" :disabled="saving">
              <LoaderCircle v-if="saving" class="spin" :size="16" aria-hidden="true" />
              <Send v-else :size="16" aria-hidden="true" />
              {{ saving ? "正在提交" : "提交申请" }}
            </button>
          </form>
        </section>

        <section class="campus-access-history" aria-labelledby="campus-history-title">
          <header><h2 id="campus-history-title">申请与决定记录</h2><button type="button" title="刷新申请状态" aria-label="刷新申请状态" @click="loadStatus"><LoaderCircle v-if="loading" class="spin" :size="16" /><span v-else>刷新</span></button></header>
          <p v-if="!status.applications.length" class="campus-access-empty">暂无申请记录</p>
          <article v-for="application in status.applications" :key="application.id" class="campus-application-history-row">
            <div class="campus-history-summary">
              <div><strong>{{ statusLabels[application.status] }}</strong><span>本人填报</span></div>
              <time :datetime="application.submittedAt">{{ dateLabel(application.submittedAt) }}</time>
            </div>
            <dl>
              <div><dt>姓名</dt><dd>{{ application.applicantName }}</dd></div>
              <div><dt>学工号</dt><dd>{{ application.studentNumber }}</dd></div>
            </dl>
            <ol v-if="application.history.length" class="campus-application-events">
              <li v-for="event in application.history" :key="event.id">
                <span>{{ eventLabel(event.action) }} · {{ event.detail }} · {{ event.actorUsername }}</span>
                <time :datetime="event.createdAt">{{ dateLabel(event.createdAt) }}</time>
                <p v-if="event.reason">理由：{{ event.reason }}</p>
              </li>
            </ol>
          </article>
        </section>
      </template>
    </main>
  </div>
</template>
