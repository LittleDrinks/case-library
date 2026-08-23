<script setup>
import { computed, onMounted, ref } from "vue";
import { Check, FilePlus2, LoaderCircle, Upload, X } from "@lucide/vue";
import { api } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const accessLevel = ref("campus");
const files = ref([]);
const job = ref(null);
const error = ref("");
const submitting = ref(false);
const candidates = ref([]);
const candidateError = ref("");
const candidateNotice = ref("");
const candidateLoading = ref(true);
const deciding = ref("");
const candidatePage = ref(1);
const candidateTotal = ref(0);
const candidatePageSize = 20;
const candidatePages = computed(() => Math.max(1, Math.ceil(
  candidateTotal.value / candidatePageSize,
)));
const accessLabels = { public: "公开", campus: "校内", private: "私密" };
const statusLabels = {
  running: "处理中", succeeded: "成功", partial_success: "部分成功",
  failed: "失败", queued: "等待处理", candidate: "待审核", duplicate: "重复",
};
const selection = computed(() => {
  if (!files.value.length) return "未选择文件";
  if (files.value.length === 1) return files.value[0].name;
  return `已选择 ${files.value.length} 个文件`;
});
const announcement = computed(() => {
  if (candidateNotice.value) return candidateNotice.value;
  if (error.value) return error.value;
  if (!job.value) return "";
  return `导入${statusLabels[job.value.status]}，共 ${job.value.itemCount} 项`;
});

function selectFiles(event) {
  files.value = Array.from(event.target.files || []);
  job.value = null;
  error.value = "";
}

function sizeLabel(size) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function itemDetail(item) {
  if (item.error) return item.error;
  return item.candidateId || item.duplicateOf || "-";
}

function defaultTitle(filename) {
  const leaf = filename.split(/[\\/]/).pop();
  return leaf.replace(/\.[^.]+$/, "") || leaf;
}

function reviewCandidate(candidate) {
  return { ...candidate, title: defaultTitle(candidate.filename) };
}

async function loadCandidates(page = candidatePage.value) {
  candidateError.value = "";
  candidateLoading.value = true;
  try {
    const result = await api.listMaterialCandidates("candidate", page, candidatePageSize);
    candidatePage.value = result.page;
    candidateTotal.value = result.total;
    candidates.value = result.items.map(reviewCandidate);
  } catch (reason) {
    candidateError.value = reason.message || "待审核素材加载失败";
  } finally {
    candidateLoading.value = false;
  }
}

function changeCandidatePage(page) {
  if (page < 1 || page > candidatePages.value || candidateLoading.value) return;
  loadCandidates(page);
}

async function refreshAfterDecision() {
  const previous = candidatePage.value > 1 && candidates.value.length === 1;
  await loadCandidates(previous ? candidatePage.value - 1 : candidatePage.value);
}

function decisionBody(candidate, decision) {
  if (decision === "reject") return { decision };
  return { decision, title: candidate.title.trim() };
}

async function decide(candidate, decision) {
  deciding.value = candidate.id;
  candidateError.value = "";
  candidateNotice.value = "";
  try {
    await api.decideMaterialCandidate(
      candidate.id, decisionBody(candidate, decision), session.csrfToken,
    );
    await refreshAfterDecision();
    const action = decision === "approve" ? `已批准入库：${candidate.title.trim()}` : `已拒绝：${candidate.filename}`;
    candidateNotice.value = action;
  } catch (reason) {
    candidateError.value = reason.message || "素材审核失败";
  } finally {
    deciding.value = "";
  }
}

async function submit() {
  error.value = "";
  job.value = null;
  submitting.value = true;
  try {
    job.value = await api.createMaterialImport(files.value, accessLevel.value, session.csrfToken);
    await loadCandidates();
  } catch (reason) {
    error.value = reason.message || "导入失败";
  } finally {
    submitting.value = false;
  }
}

onMounted(loadCandidates);
</script>

<template>
  <div class="admin-page">
    <SiteHeader />
    <main id="main-content" class="material-import-main">
      <header class="material-import-heading">
        <div>
          <p>素材管理</p>
          <h1>资料批量导入</h1>
        </div>
      </header>

      <form class="material-import-form" @submit.prevent="submit">
        <label class="material-file-button" title="选择资料">
          <FilePlus2 :size="19" aria-hidden="true" />
          <input type="file" multiple required aria-label="选择资料" @change="selectFiles" />
        </label>
        <span class="material-file-selection" :title="selection">{{ selection }}</span>
        <label class="material-access-field">
          <span>访问级别</span>
          <select v-model="accessLevel" aria-label="素材访问级别">
            <option value="public">公开</option>
            <option value="campus">校内</option>
            <option value="private">私密</option>
          </select>
        </label>
        <button class="material-import-submit" type="submit" :disabled="submitting || !files.length">
          <LoaderCircle v-if="submitting" class="spin" :size="17" aria-hidden="true" />
          <Upload v-else :size="17" aria-hidden="true" />
          <span>{{ submitting ? "导入中" : "开始导入" }}</span>
        </button>
      </form>

      <p v-if="error" class="material-import-error" role="alert">{{ error }}</p>
      <p :class="candidateNotice ? 'material-review-notice' : 'material-live-status'" role="status" aria-live="polite">{{ announcement }}</p>
      <section class="material-review" aria-labelledby="material-review-title">
        <header>
          <div><p>入库审核</p><h2 id="material-review-title">待审核素材</h2></div>
          <span>共 {{ candidateTotal }} 项</span>
        </header>
        <p v-if="candidateError" class="material-import-error" role="alert">{{ candidateError }}</p>
        <p v-else-if="candidateLoading" class="material-review-empty">正在加载待审核素材</p>
        <p v-else-if="!candidates.length" class="material-review-empty">暂无待审核素材</p>
        <div v-else class="material-review-list">
          <article v-for="candidate in candidates" :key="candidate.id" :aria-label="`待审核：${candidate.filename}`">
            <div class="material-review-file">
              <b :title="candidate.filename">{{ candidate.filename }}</b>
              <span>{{ sizeLabel(candidate.size) }} · {{ accessLabels[candidate.accessLevel] }}</span>
            </div>
            <label><span>素材标题</span><input v-model="candidate.title" :aria-label="`素材标题：${candidate.filename}`" maxlength="300" /></label>
            <div class="material-review-actions">
              <button type="button" :aria-label="`拒绝候选：${candidate.filename}`" :disabled="deciding === candidate.id" @click="decide(candidate, 'reject')"><X :size="15" />拒绝</button>
              <button type="button" :aria-label="`批准入库：${candidate.filename}`" :disabled="deciding === candidate.id || !candidate.title.trim()" @click="decide(candidate, 'approve')"><LoaderCircle v-if="deciding === candidate.id" class="spin" :size="15" /><Check v-else :size="15" />批准入库</button>
            </div>
          </article>
        </div>
        <nav v-if="candidateTotal > candidatePageSize" class="material-review-pagination" aria-label="待审核素材分页">
          <span>第 {{ candidatePage }} 页，共 {{ candidatePages }} 页</span>
          <div><button type="button" :disabled="candidatePage === 1 || candidateLoading" @click="changeCandidatePage(candidatePage - 1)">上一页</button><button type="button" :disabled="candidatePage === candidatePages || candidateLoading" @click="changeCandidatePage(candidatePage + 1)">下一页</button></div>
        </nav>
      </section>
      <section
        v-if="job"
        class="material-import-results"
        aria-labelledby="material-result-title"
      >
        <header>
          <div>
            <h2 id="material-result-title">导入结果</h2>
            <span>{{ job.itemCount }} 项 · {{ accessLabels[job.accessLevel] }}</span>
          </div>
          <strong :data-status="job.status">{{ statusLabels[job.status] }}</strong>
        </header>
        <div class="material-result-scroll" role="region" aria-label="导入明细" tabindex="0">
          <table>
            <thead>
              <tr><th>文件</th><th>大小</th><th>状态</th><th>记录</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in job.items" :key="item.id">
                <td :title="item.filename">{{ item.filename }}</td>
                <td>{{ sizeLabel(item.size) }}</td>
                <td>
                  <span class="material-item-status" :data-status="item.status">
                    {{ statusLabels[item.status] }}
                  </span>
                </td>
                <td :title="itemDetail(item)">{{ itemDetail(item) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
</template>
