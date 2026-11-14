<script setup>
import { Bot, LayoutDashboard, PackageOpen, Puzzle, Tags } from "@lucide/vue";
import { useRoute } from "vue-router";
import SiteHeader from "./SiteHeader.vue";
const route = useRoute();
const links = [
  { name: "admin-dashboard", label: "管理概览", icon: LayoutDashboard },
  { name: "material-imports", label: "素材入库", icon: PackageOpen },
  { name: "admin-skills", label: "Skill 管理", icon: Puzzle },
  { name: "admin-tag-catalog", label: "标签目录", icon: Tags },
  { name: "admin-ai-settings", label: "平台 AI", icon: Bot },
];
</script>

<template>
  <div class="admin-page admin-shell" :class="{ 'admin-shell-review': route.name === 'case-review' }">
    <SiteHeader />
    <div class="admin-main admin-dashboard">
      <aside class="admin-sidebar">
        <span class="admin-sidebar-label">平台管理</span>
        <nav aria-label="管理工具">
          <RouterLink v-for="link in links" :key="link.name" :to="{ name: link.name }"
                      exact-active-class="is-active"
                      :class="{ 'is-active': link.name === 'admin-dashboard' && route.name === 'case-review' }">
            <component :is="link.icon" :size="18" />{{ link.label }}
          </RouterLink>
        </nav>
      </aside>
      <component :is="route.name === 'case-review' ? 'div' : 'main'"
                 :id="route.name === 'case-review' ? undefined : 'main-content'"
                 class="admin-content">
        <RouterView v-slot="{ Component }"><component :is="Component" :key="route.fullPath" /></RouterView>
      </component>
    </div>
  </div>
</template>
