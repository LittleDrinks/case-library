<script setup>
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, Check, LoaderCircle, RefreshCw } from "@lucide/vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import SiteHeader from "../components/SiteHeader.vue";
import { session } from "../session.js";

const router = useRouter();
const catalog = ref(null);
const loading = ref(true);
const creating = ref(false);
const catalogError = ref("");
const creationError = ref("");
const stageId = ref("");
const typeId = ref("");
const templateId = ref("");
const stages = computed(() => catalog.value?.stages || []);
const caseTypes = computed(() => catalog.value?.caseTypes || []);
const compatibleTemplates = computed(() => (catalog.value?.templates || []).filter((template) => (
  template.stageIds.includes(stageId.value) && template.typeIds.includes(typeId.value)
)));

function selectStage(id) {
  stageId.value = id;
  typeId.value = "";
  templateId.value = "";
}

function selectType(id) {
  typeId.value = id;
  templateId.value = "";
}

async function loadCatalog() {
  loading.value = true;
  catalogError.value = "";
  try {
    catalog.value = await api.caseCreationCatalog();
  } catch (reason) {
    catalogError.value = reason.message || "新建目录加载失败";
  } finally {
    loading.value = false;
  }
}

async function createCase() {
  if (!templateId.value || creating.value) return;
  creating.value = true;
  creationError.value = "";
  try {
    const created = await api.createCase({
      stageId: stageId.value, typeId: typeId.value, templateId: templateId.value,
    }, session.csrfToken);
    await router.push({ name: "workbench", params: { id: created.id } });
  } catch (reason) {
    creationError.value = reason.message || "新建案例失败";
  } finally {
    creating.value = false;
  }
}

onMounted(loadCatalog);
</script>

<template>
  <div class="home-page">
    <SiteHeader />
    <main id="main-content" class="home-main new-case-main">
      <header class="new-case-heading">
        <div><span class="home-eyebrow">教学工作</span><h1>新建案例</h1></div>
        <button type="button" class="new-case-back" @click="router.push({ name: 'my-cases' })">
          返回我的案例
        </button>
      </header>

      <div v-if="loading" class="catalog-state">
        <LoaderCircle class="spin" :size="22" /><span>正在加载新建目录</span>
      </div>
      <div v-else-if="catalogError" class="catalog-state error-state" role="alert">
        <AlertTriangle :size="22" /><span>{{ catalogError }}</span>
        <button type="button" @click="loadCatalog"><RefreshCw :size="15" />重试</button>
      </div>
      <form v-else class="creation-flow" @submit.prevent="createCase">
        <section class="creation-step" aria-labelledby="stage-heading">
          <header><span>01</span><div><h2 id="stage-heading">选择学段</h2></div></header>
          <div class="stage-options" role="radiogroup" aria-label="学段">
            <button
              v-for="stage in stages"
              :key="stage.id"
              type="button"
              role="radio"
              :aria-label="stage.name"
              :aria-checked="stageId === stage.id"
              :class="{ selected: stageId === stage.id }"
              @click="selectStage(stage.id)"
            >{{ stage.name }}</button>
          </div>
        </section>

        <section v-if="stageId" class="creation-step" aria-labelledby="type-heading">
          <header><span>02</span><div><h2 id="type-heading">选择案例类型</h2></div></header>
          <div class="type-options">
            <button
              v-for="caseType in caseTypes"
              :key="caseType.id"
              type="button"
              :aria-pressed="typeId === caseType.id"
              :class="{ selected: typeId === caseType.id }"
              @click="selectType(caseType.id)"
            ><b>{{ caseType.name }}</b><span>{{ caseType.description }}</span></button>
          </div>
        </section>

        <section v-if="typeId" class="creation-step" aria-labelledby="template-heading">
          <header><span>03</span><div><h2 id="template-heading">选择模板</h2></div></header>
          <div class="template-options">
            <button
              v-for="template in compatibleTemplates"
              :key="template.id"
              type="button"
              :aria-pressed="templateId === template.id"
              :class="{ selected: templateId === template.id }"
              @click="templateId = template.id"
            >
              <span>
                <b>{{ template.name }}</b>
                <Check v-if="templateId === template.id" :size="17" />
              </span>
              <ul><li v-for="title in template.sectionTitles" :key="title">{{ title }}</li></ul>
            </button>
          </div>
        </section>

        <footer class="creation-actions">
          <p v-if="creationError" class="creation-error" role="alert">{{ creationError }}</p>
          <p v-else-if="!templateId">请选择学段、案例类型和模板后创建。</p>
          <button type="submit" :disabled="!templateId || creating">
            <LoaderCircle v-if="creating" class="spin" :size="17" aria-hidden="true" />
            {{ creating ? "正在创建" : "创建案例" }}
          </button>
        </footer>
      </form>
    </main>
  </div>
</template>
