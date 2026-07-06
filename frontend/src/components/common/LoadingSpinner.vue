<script setup>
defineProps({
  size: { type: String, default: 'md' }, // 'sm', 'md', 'lg'
})
</script>

<template>
  <div class="loading-spinner" :class="`spinner-${size}`">
    <div class="spinner"></div>
  </div>
</template>

<style scoped>
.loading-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner-sm .spinner { width: 20px; height: 20px; border-width: 2px; }
.spinner-md .spinner { width: 36px; height: 36px; border-width: 3px; }
.spinner-lg .spinner { width: 48px; height: 48px; border-width: 4px; }
</style>
