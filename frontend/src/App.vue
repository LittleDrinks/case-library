<template>
  <RouterView v-slot="{ Component, route }">
    <Transition name="page" mode="out-in">
      <component :is="Component" :key="route.meta.adminLayout ? 'admin' : route.name === 'search' ? 'search' : route.fullPath" />
    </Transition>
  </RouterView>
</template>
