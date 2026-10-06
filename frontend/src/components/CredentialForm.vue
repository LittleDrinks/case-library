<script setup>
import { ArrowRight, LoaderCircle } from "@lucide/vue";

defineProps({
  username: { type: String, required: true },
  password: { type: String, required: true },
  error: { type: String, default: "" },
  submitting: { type: Boolean, default: false },
  passwordAutocomplete: { type: String, required: true },
  passwordHint: { type: String, default: "" },
  submitLabel: { type: String, required: true },
  submittingLabel: { type: String, required: true },
});

defineEmits(["update:username", "update:password", "submit"]);
</script>

<template>
  <form class="login-form" @submit.prevent="$emit('submit')">
    <label>
      <span>用户名</span>
      <input
        :value="username"
        name="username"
        autocomplete="username"
        maxlength="80"
        autofocus
        required
        @input="$emit('update:username', $event.target.value)"
      />
    </label>
    <label>
      <span>密码</span>
      <input
        :value="password"
        name="password"
        type="password"
        :autocomplete="passwordAutocomplete"
        maxlength="128"
        required
        @input="$emit('update:password', $event.target.value)"
      />
    </label>
    <p v-if="passwordHint" class="field-hint">{{ passwordHint }}</p>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button class="login-submit" type="submit" :disabled="submitting">
      <LoaderCircle v-if="submitting" :size="17" class="spin" aria-hidden="true" />
      <span>{{ submitting ? submittingLabel : submitLabel }}</span>
      <ArrowRight v-if="!submitting" :size="17" aria-hidden="true" />
    </button>
  </form>
</template>
