<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { usePortfolioStore } from '../stores/portfolio'
import AppSidebar from '../components/layout/AppSidebar.vue'

const router = useRouter()
const authStore = useAuthStore()
const portfolioStore = usePortfolioStore()

const capital = ref('')
const step = ref('input') // 'input' | 'optimizing' | 'result'
const isChecking = ref(true)

onMounted(async () => {
  await authStore.fetchUser()
  if (authStore.hasPortfolio) {
    router.push('/')
  } else {
    isChecking.value = false
  }
})

async function handleInitialize() {
  const amount = parseFloat(capital.value)
  if (!amount || amount <= 0) return

  step.value = 'optimizing'
  const result = await portfolioStore.initializePortfolio(amount)
  if (result) {
    step.value = 'result'
  } else {
    step.value = 'input'
  }
}

function goToTrading() {
  router.push('/trading')
}

function formatCurrency(value) {
  return '₹' + Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
</script>

<template>
  <div class="app-layout">
    <AppSidebar />

    <main class="main-content">
      <div v-if="isChecking" class="loading-overlay">
        <div class="spinner"></div>
        <p>Loading...</p>
      </div>
      
      <!-- Step 1: Capital Input -->
      <div v-else-if="step === 'input'" class="portfolio-init">
        <div class="init-card">
          <div class="init-icon">🧠</div>
          <h1>Initialize Your Portfolio</h1>
          <p class="text-secondary mb-lg">
            Enter the amount of capital you wish to invest. Our PPO-based AI will
            analyze 10 diversified NSE stocks and generate an optimal portfolio allocation.
          </p>

          <div v-if="portfolioStore.error" class="error-message">
            {{ portfolioStore.error }}
          </div>

          <div class="input-group">
            <label for="capital-input">Investment Capital (₹)</label>
            <input
              id="capital-input"
              v-model="capital"
              type="number"
              class="input"
              placeholder="e.g., 500000"
              min="10000"
              max="10000000"
              step="10000"
              style="font-size: var(--font-size-xl); text-align: center;"
            />
          </div>

          <button
            class="btn btn-primary btn-lg w-full"
            :disabled="!capital || parseFloat(capital) <= 0 || parseFloat(capital) > 10000000"
            @click="handleInitialize"
          >
            🚀 Optimize Portfolio with PPO
          </button>

          <p class="text-muted mt-md" style="font-size: var(--font-size-xs);">
            Maximum investment: ₹1,00,00,000
          </p>
        </div>
      </div>

      <!-- Step 2: Optimizing Animation -->
      <div v-else-if="step === 'optimizing'" class="loading-overlay">
        <div class="spinner" style="width:48px;height:48px;border-width:4px;"></div>
        <h2>Running PPO Portfolio Optimization...</h2>
        <p class="text-secondary">Analyzing 10 NSE stocks across multiple sectors</p>
      </div>

      <!-- Step 3: Results -->
      <div v-else-if="step === 'result' && portfolioStore.allocation">
        <div class="page-header">
          <h1>✅ Portfolio Optimized</h1>
          <p>PPO has generated optimal weights for your {{ formatCurrency(portfolioStore.allocation.total_capital) }} portfolio</p>
        </div>

        <div class="stats-grid" style="margin-bottom: var(--space-xl);">
          <div class="stat-card">
            <div class="stat-label">Total Capital</div>
            <div class="stat-value">{{ formatCurrency(portfolioStore.allocation.total_capital) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Cash After Allocation</div>
            <div class="stat-value">{{ formatCurrency(portfolioStore.allocation.cash_after_allocation) }}</div>
          </div>
        </div>

        <!-- Allocation Table -->
        <div class="card mb-lg">
          <h2 style="margin-bottom: var(--space-lg); font-size: var(--font-size-xl);">
            Target Allocations
          </h2>
          <table class="data-table">
            <thead>
              <tr>
                <th>Stock</th>
                <th>Sector</th>
                <th>Weight</th>
                <th>Target Amount</th>
                <th>Shares</th>
                <th>Price</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="alloc in portfolioStore.allocation.allocations" :key="alloc.stock_symbol">
                <td class="font-bold">{{ alloc.stock_name }}</td>
                <td><span class="badge badge-info">{{ alloc.sector }}</span></td>
                <td class="font-mono">{{ (alloc.weight * 100).toFixed(2) }}%</td>
                <td class="font-mono">{{ formatCurrency(alloc.target_amount) }}</td>
                <td class="font-bold">{{ alloc.target_quantity }}</td>
                <td class="font-mono">{{ formatCurrency(alloc.current_price) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="text-center">
          <button class="btn btn-primary btn-lg" @click="goToTrading">
            📈 Execute Trades with Algorithmic Trading
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.portfolio-init {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 70vh;
}

.init-card {
  max-width: 520px;
  width: 100%;
  text-align: center;
  background: var(--bg-card);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  padding: var(--space-2xl);
}

.init-icon {
  font-size: 3rem;
  margin-bottom: var(--space-lg);
}

.init-card h1 {
  font-size: var(--font-size-2xl);
  margin-bottom: var(--space-sm);
}
</style>
