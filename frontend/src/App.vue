<template>
  <RouterView v-slot="{ Component, route }">
    <component :is="Component" :key="route.name === 'search' ? 'search' : route.fullPath" />
  </RouterView>
</template>
