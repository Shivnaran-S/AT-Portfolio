<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { usePortfolioStore } from '../stores/portfolio'
import AppSidebar from '../components/layout/AppSidebar.vue'
import api from '../composables/useApi'

const authStore = useAuthStore()
const portfolioStore = usePortfolioStore()

const orders = ref([])
const executing = ref(false)
const executionResult = ref(null)
const loading = ref(true)

onMounted(async () => {
  await loadOrders()
  loading.value = false
})

async function loadOrders() {
  try {
    const response = await api.get('/trading/orders')
    orders.value = response.data
  } catch (err) {
    console.error('Failed to load orders:', err)
  }
}

async function executeTrades() {
  executing.value = true
  executionResult.value = null
  try {
    const response = await api.post('/trading/execute')
    executionResult.value = response.data
    await loadOrders()
    await portfolioStore.fetchStatus()
  } catch (err) {
    console.error('Trade execution failed:', err)
  } finally {
    executing.value = false
  }
}

function formatCurrency(value) {
  return '₹' + Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatTime(isoString) {
  if (!isoString) return '—'
  const date = new Date(isoString)
  return date.toLocaleString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}
</script>

<template>
  <div class="app-layout">
    <AppSidebar />

    <main class="main-content">
      <div class="page-header flex justify-between items-center">
        <div>
          <h1>Algorithmic Trading</h1>
          <p>PPO-powered order execution with optimal timing and slicing</p>
        </div>
        <button
          class="btn btn-primary btn-lg"
          :disabled="executing"
          @click="executeTrades"
        >
          <span v-if="executing" class="spinner" style="width:18px;height:18px;border-width:2px;"></span>
          <span v-else>⚡ Execute All Trades</span>
        </button>
      </div>

      <!-- Execution Result -->
      <div v-if="executionResult" class="card mb-lg">
        <div class="flex items-center gap-md mb-lg">
          <span style="font-size:1.5rem;">✅</span>
          <h2 style="font-size: var(--font-size-xl);">{{ executionResult.message }}</h2>
        </div>

        <div v-for="order in executionResult.orders" :key="order.id" class="execution-card mb-md">
          <div class="flex justify-between items-center mb-md">
            <div class="flex items-center gap-md">
              <span class="badge" :class="order.order_type === 'BUY' ? 'badge-success' : 'badge-danger'">
                {{ order.order_type }}
              </span>
              <strong>{{ order.stock_symbol }}</strong>
            </div>
            <span class="text-secondary">
              {{ order.filled_quantity }} / {{ order.total_quantity }} shares
            </span>
          </div>

          <!-- Order Slices Timeline -->
          <div class="timeline">
            <div
              v-for="(slice, idx) in order.slices"
              :key="idx"
              class="timeline-item"
            >
              <div class="timeline-dot"></div>
              <div class="timeline-content">
                <div class="flex justify-between">
                  <span class="font-bold">{{ slice.quantity }} shares</span>
                  <span class="font-mono text-secondary">@ {{ formatCurrency(slice.price) }}</span>
                </div>
                <div class="text-muted" style="font-size: var(--font-size-xs);">
                  {{ formatTime(slice.time) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="loading-overlay">
        <div class="spinner"></div>
        <p>Loading orders...</p>
      </div>

      <!-- Order History -->
      <div v-else class="card">
        <h2 style="margin-bottom: var(--space-lg); font-size: var(--font-size-xl);">
          Order History
        </h2>

        <div v-if="orders.length === 0" class="text-center text-secondary" style="padding:var(--space-2xl);">
          <p style="font-size:2rem;">📋</p>
          <p class="mt-md">No orders yet. Initialize your portfolio and execute trades.</p>
        </div>

        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Stock</th>
              <th>Quantity</th>
              <th>Filled</th>
              <th>Status</th>
              <th>Slices</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id">
              <td>
                <span class="badge" :class="order.order_type === 'BUY' ? 'badge-success' : 'badge-danger'">
                  {{ order.order_type }}
                </span>
              </td>
              <td class="font-bold">{{ order.stock_symbol }}</td>
              <td>{{ order.total_quantity }}</td>
              <td>{{ order.filled_quantity }}</td>
              <td>
                <span class="badge" :class="{
                  'badge-success': order.status === 'FILLED',
                  'badge-warning': order.status === 'PARTIAL',
                  'badge-info': order.status === 'PENDING',
                  'badge-danger': order.status === 'CANCELLED',
                }">{{ order.status }}</span>
              </td>
              <td>{{ order.slices?.length || 0 }}</td>
              <td class="text-secondary">{{ formatTime(order.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>

<style scoped>
.execution-card {
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  padding-left: var(--space-md);
  border-left: 2px solid var(--accent-primary);
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  position: relative;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent-primary);
  margin-top: 6px;
  margin-left: -22px;
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
}

.timeline-content {
  flex: 1;
  padding: var(--space-sm) 0;
}
</style>
