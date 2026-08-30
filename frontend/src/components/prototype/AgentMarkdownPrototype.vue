<script setup>
import MarkdownIt from "markdown-it";
import { computed } from "vue";

const props = defineProps({ content: { type: String, required: true } });
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true });
const rendered = computed(() => markdown.render(props.content));
</script>

<template>
  <div class="agent-markdown" v-html="rendered"></div>
</template>
