<script setup>
import { Download, LockKeyhole } from "@lucide/vue";
import { api } from "../api.js";

defineProps({ material: { type: Object, required: true }, showLabel: { type: Boolean, default: false } });
</script>

<template>
  <a
    v-if="material.contentAvailable && material.hasFile"
    class="material-download"
    :class="{ labeled: showLabel }"
    :href="api.materialContentUrl(material.id)"
    :aria-label="`下载${material.title}`"
    :title="`下载 ${material.filename || material.title}`"
    download
  ><Download :size="16" aria-hidden="true" /><span v-if="showLabel">下载原文件</span></a>
  <button
    v-else-if="material.hasFile"
    class="material-download restricted"
    :class="{ labeled: showLabel }"
    type="button"
    :aria-label="`${material.title}内容受限`"
    title="当前账号无权下载"
    disabled
  ><LockKeyhole :size="15" aria-hidden="true" /><span v-if="showLabel">无权下载</span></button>
</template>
