<script setup>
import { computed, ref, watch } from "vue";
import { Check, LoaderCircle, Search } from "@lucide/vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api.js";
import CatalogPagination from "../components/CatalogPagination.vue";
import MaterialDownloadAction from "../components/MaterialDownloadAction.vue";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const route = useRoute();
const router = useRouter();
const query = ref("");
const materials = ref([]);
const facets = ref({});
const authority = ref("");
const materialType = ref("");
const externalOnly = ref(false);
const error = ref("");
const notice = ref("");
const busy = ref(false);
const selected = ref([]);
const mounted = ref([]);
const caseRecord = ref(null);
const viewMode = ref("all");
const page = ref(1);
const cursor = ref("");
const total = ref(0);
const nextCursor = ref(null);
const previousCursor = ref(null);
const caseId = computed(() => String(route.query.caseId || ""));
const types = computed(() => facets.value.materialType || []);
const mountedIds = computed(() => new Set(mounted.value.map(item => item.id)));
const availableIds = computed(() => new Set(
  materials.value.filter(item => item.contentAvailable).map(item => item.id),
));
const visibleCount = computed(() => {
  if (!authority.value) return total.value;
  const rows = facets.value.authority || [];
  return rows.reduce((sum, row) => sum + row.count, 0);
});
const editable = computed(() => Boolean(caseRecord.value
  && caseRecord.value.ownerId === session.user?.id
  && caseRecord.value.workflowStatus === "draft"));
let searchGeneration = 0;

function facetCount(name, value) {
  return facets.value[name]?.find(row => row.value === value)?.count || 0;
}

function searchFilters() {
  return {
    ...(authority.value ? { authority: [authority.value] } : {}),
    ...(materialType.value ? { materialType: [materialType.value] } : {}),
    ...(externalOnly.value ? { accessLevel: "public" } : {}),
    ...(viewMode.value === "mounted" ? { mountedInCaseId: caseId.value } : {}),
  };
}

async function load(activeCursor = cursor.value) {
  const current = ++searchGeneration;
  error.value = "";
  try {
    const payload = await api.search(query.value.trim(), "material", activeCursor, 50, searchFilters());
    if (current !== searchGeneration) return;
    materials.value = payload.items;
    updateMetadata(payload);
    page.value = payload.page;
    nextCursor.value = payload.nextCursor;
    previousCursor.value = payload.previousCursor;
  } catch (caught) {
    if (current === searchGeneration) error.value = caught.message || "素材加载失败";
  }
}

function updateMetadata(payload) {
  if (!payload.metadataIncluded) return;
  facets.value = payload.facets;
  total.value = payload.total;
}

function routeQuery(overrides = {}) {
  const state = {
    q: query.value.trim(), authority: authority.value, materialType: materialType.value,
    publicOnly: externalOnly.value, view: viewMode.value, ...overrides,
  };
  return {
    ...(caseId.value ? { caseId: caseId.value } : {}), ...(state.q ? { q: state.q } : {}),
    ...(state.authority ? { authority: state.authority } : {}),
    ...(state.materialType ? { materialType: state.materialType } : {}),
    ...(state.publicOnly ? { accessLevel: "public" } : {}),
    ...(state.view === "mounted" ? { view: "mounted" } : {}),
  };
}

function updateRoute(overrides) {
  selected.value = [];
  cursor.value = "";
  router.replace({ name: "materials", query: routeQuery(overrides) });
}

function submitSearch() {
  updateRoute({ q: query.value.trim() });
}

function selectPage(nextCursor) {
  cursor.value = nextCursor;
  load(nextCursor);
}

async function loadContext() {
  caseRecord.value = null;
  mounted.value = [];
  if (!caseId.value) return;
  try {
    [caseRecord.value, mounted.value] = await Promise.all([
      api.getCase(caseId.value), api.listCaseMaterials(caseId.value),
    ]);
  } catch (caught) {
    error.value = caught.message || "素材掌控台加载失败";
  }
}

async function refreshRevision() {
  caseRecord.value = await api.getCase(caseId.value);
}

async function mountOne(materialId) {
  await api.mountCaseMaterial(
    caseId.value, materialId, caseRecord.value.revision, session.csrfToken,
  );
  await refreshRevision();
}

async function mountSelected() {
  const ids = selected.value.filter(id => availableIds.value.has(id));
  if (!editable.value || busy.value || !ids.length) return;
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    for (const id of ids) await mountOne(id);
    mounted.value = await api.listCaseMaterials(caseId.value);
    notice.value = `已加入 ${ids.length} 条素材`;
    selected.value = [];
  } catch (caught) {
    error.value = caught.message || "素材加入失败";
  } finally {
    busy.value = false;
  }
}

function selectView(mode) {
  if (["original", "pending"].includes(mode)) {
    updateRoute({ view: "all", authority: mode });
    return;
  }
  updateRoute({ view: mode, authority: mode === "all" ? "" : authority.value });
}

function selectFilter(name, value) {
  updateRoute({ [name]: value });
}

function selectExternal(event) {
  updateRoute({ publicOnly: event.target.checked });
}

function syncSearchRoute() {
  query.value = String(route.query.q || "");
  authority.value = String(route.query.authority || "");
  materialType.value = String(route.query.materialType || "");
  externalOnly.value = route.query.accessLevel === "public";
  viewMode.value = route.query.view === "mounted" && caseId.value ? "mounted" : "all";
  cursor.value = "";
  load(null);
}

watch(() => route.fullPath, syncSearchRoute, { immediate: true });
watch(caseId, loadContext, { immediate: true });
</script>

<template>
  <div class="home-page material-page">
    <SiteHeader />
    <main id="main-content" class="material-shell">
      <header class="material-heading">
        <div><span class="home-eyebrow">资源检索</span><h1>素材掌控台</h1><p>检索、筛选并将真实素材带回案例编写</p></div>
        <RouterLink v-if="caseId" :to="{ name: 'workbench', params: { id: caseId } }">返回当前案例</RouterLink>
      </header>
      <div class="material-explorer">
        <aside class="material-filter">
          <h2>工作视图</h2>
          <button v-if="caseId" :class="{ active: viewMode === 'mounted' }" type="button" @click="selectView('mounted')"><span>当前案例候选</span><b>{{ mounted.length }}</b></button>
          <button :class="{ active: viewMode === 'all' && authority === 'original' }" type="button" @click="selectView('original')"><span>最新权威材料</span><b>{{ facetCount('authority', 'original') }}</b></button>
          <button :class="{ active: viewMode === 'all' && authority === 'pending' }" type="button" @click="selectView('pending')"><span>需复核来源</span><b>{{ facetCount('authority', 'pending') }}</b></button>
          <button :class="{ active: viewMode === 'all' && !authority }" type="button" @click="selectView('all')"><span>全部可见素材</span><b>{{ visibleCount }}</b></button>
          <fieldset><legend>来源权威性</legend><label><input name="authority" type="radio" :checked="!authority" @change="selectFilter('authority', '')" /><span>全部</span><small>{{ visibleCount }}</small></label><label><input name="authority" type="radio" :checked="authority === 'original'" @change="selectFilter('authority', 'original')" /><span>原始权威</span><small>{{ facetCount('authority', 'original') }}</small></label><label><input name="authority" type="radio" :checked="authority === 'secondary'" @change="selectFilter('authority', 'secondary')" /><span>可靠二手</span><small>{{ facetCount('authority', 'secondary') }}</small></label><label><input name="authority" type="radio" :checked="authority === 'pending'" @change="selectFilter('authority', 'pending')" /><span>待核验</span><small>{{ facetCount('authority', 'pending') }}</small></label></fieldset>
          <fieldset><legend>素材类型</legend><label><input name="material-type" type="radio" :checked="!materialType" @change="selectFilter('materialType', '')" />全部</label><label v-for="item in types" :key="item.value"><input name="material-type" type="radio" :checked="materialType === item.value" @change="selectFilter('materialType', item.value)" />{{ item.value }} <small>{{ item.count }}</small></label></fieldset>
          <fieldset><legend>使用条件</legend><label><input type="checkbox" :checked="externalOnly" @change="selectExternal" /><span>仅可对外使用</span><small>{{ facetCount('accessLevel', 'public') }}</small></label></fieldset>
        </aside>
        <section class="material-results">
          <form role="search" @submit.prevent="submitSearch"><Search :size="17" /><input v-model="query" aria-label="搜索素材" placeholder="检索素材" /><button>搜索</button></form>
          <div v-if="caseId" class="material-selection-bar">
            <span v-if="editable">已选择 {{ selected.length }} 条</span>
            <span v-else>当前案例不可修改素材</span>
            <button type="button" aria-label="加入当前案例" :disabled="!selected.length || busy || !editable" @click="mountSelected">
              <LoaderCircle v-if="busy" class="spin" :size="15" />
              <Check v-else :size="15" />{{ busy ? "正在加入" : "加入当前案例" }}
            </button>
          </div>
          <p v-if="error" class="error-state" role="alert">{{ error }}</p>
          <p v-else-if="notice" class="material-notice" role="status">{{ notice }}</p>
          <div v-else class="material-table-wrap">
            <table><thead><tr><th v-if="caseId" class="selection-column">选择</th><th>素材</th><th>来源</th><th>类型</th><th>权威性</th><th class="download-column">下载</th></tr></thead><tbody><tr v-for="item in materials" :key="item.id"><td v-if="caseId" class="selection-column" data-label="选择"><span v-if="mountedIds.has(item.id)" class="mounted-label">已加入</span><input v-else v-model="selected" type="checkbox" :value="item.id" :aria-label="`选择${item.title}`" :disabled="!item.contentAvailable || !editable || busy" /></td><td data-label="素材"><b>{{ item.title }}</b><small>{{ item.summary }}</small></td><td data-label="来源">{{ item.source }}</td><td data-label="类型">{{ item.materialType }}</td><td data-label="权威性">{{ { original: '原始权威来源', secondary: '可靠二手来源', pending: '待核验线索' }[item.authority] }}</td><td class="download-column" data-label="下载"><MaterialDownloadAction :material="item" /></td></tr></tbody></table>
            <p v-if="!materials.length" class="search-empty">当前筛选下没有结果</p>
            <CatalogPagination v-if="total" :page="page" :total="total" :next-cursor="nextCursor" :previous-cursor="previousCursor" @change="selectPage" />
          </div>
        </section>
      </div>
    </main>
  </div>
</template>
