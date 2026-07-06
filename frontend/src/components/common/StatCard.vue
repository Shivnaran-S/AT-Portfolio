<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  change: { type: String, default: '' },
  isPositive: { type: Boolean, default: true },
  icon: { type: String, default: '📊' },
})
</script>

<template>
  <div class="stat-card">
    <div class="flex justify-between items-center">
      <span class="stat-label">{{ label }}</span>
      <span class="stat-icon">{{ icon }}</span>
    </div>
    <div class="stat-value">{{ value }}</div>
    <div v-if="change" class="stat-change" :class="isPositive ? 'positive' : 'negative'">
      {{ change }}
    </div>
  </div>
</template>

<style scoped>
.stat-icon {
  font-size: 1.3rem;
  opacity: 0.7;
}
</style>
