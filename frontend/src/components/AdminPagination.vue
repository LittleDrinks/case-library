<script setup>
import { ElConfigProvider, ElPagination } from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import "element-plus/es/components/pagination/style/css";
import "element-plus/es/components/select/style/css";
import "element-plus/es/components/input/style/css";
defineProps({ total: { type: Number, required: true }, page: { type: Number, required: true },
  pageSize: { type: Number, required: true }, loading: Boolean, label: { type: String, default: "列表分页" } });
defineEmits(["page", "page-size"]);
</script>
<template>
  <nav class="admin-pagination" :aria-label="label">
    <span>共 {{ total.toLocaleString() }} 条 · 第 {{ page }} 页，共 {{ Math.max(1, Math.ceil(total / pageSize)) }} 页</span>
    <ElConfigProvider :locale="zhCn"><ElPagination :total="total" :current-page="page" :page-size="pageSize" :page-sizes="[10, 20, 50]"
                  :pager-count="5" :disabled="loading" layout="prev, pager, next, sizes, jumper"
                  @update:current-page="$emit('page', $event)" @update:page-size="$emit('page-size', $event)" /></ElConfigProvider>
  </nav>
</template>
