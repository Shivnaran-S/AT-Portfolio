<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { usePortfolioStore } from '../stores/portfolio'
import AppSidebar from '../components/layout/AppSidebar.vue'
import api from '../composables/useApi'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const portfolioStore = usePortfolioStore()

const isChecking = ref(true)
const step = ref('input') // 'input' | 'previewing' | 'preview' | 'trading'

const action = computed(() => route.query.action || 'initialize')
const inputAmount = ref('')
const previewPlan = ref(null)

// Live trading state
const executionStatus = ref(null)
const isExecuting = ref(false)
const isStopped = ref(false)
let pollingInterval = null

onMounted(async () => {
  await authStore.fetchUser()
  
  if (action.value === 'initialize' && authStore.hasPortfolio) {
    router.push('/')
    return
  }
  
  isChecking.value = false
  
  // Auto-skip input step if rebalancing, adding funds, or withdrawing funds
  if (action.value === 'rebalance') {
    handlePreview()
  } else if (action.value === 'add_funds' || action.value === 'withdraw_funds') {
    const amt = route.query.amount
    if (amt && parseFloat(amt) > 0) {
      inputAmount.value = amt
      handlePreview()
    }
  }
})

onUnmounted(() => {
  if (pollingInterval) clearInterval(pollingInterval)
})

async function handlePreview() {
  let amount = 0
  if (action.value !== 'rebalance') {
    amount = parseFloat(inputAmount.value)
    if (!amount || amount <= 0) return
  }

  step.value = 'previewing'
  
  let result = null
  if (action.value === 'initialize') {
    result = await portfolioStore.previewInitialize(amount)
  } else if (action.value === 'withdraw_funds') {
    result = await portfolioStore.previewWithdraw(amount)
  } else if (action.value === 'add_funds') {
    await portfolioStore.addFunds(amount) // Adds cash to wallet
    result = await portfolioStore.previewRebalance()
  } else if (action.value === 'rebalance') {
    result = await portfolioStore.previewRebalance()
  }

  if (result) {
    previewPlan.value = result
    step.value = 'preview'
  } else {
    // Error occurred, go back to input or dashboard
    if (action.value === 'initialize') step.value = 'input'
    else router.push('/')
  }
}

async function handleConfirm() {
  step.value = 'trading'
  isExecuting.value = true
  portfolioStore.error = null
  
  try {
    let confirmResult = null
    // 1. Confirm plan to generate orders in DB
    if (action.value === 'initialize') {
      confirmResult = await portfolioStore.confirmInitialize(previewPlan.value)
    } else if (action.value === 'withdraw_funds') {
      // Need to extract amount from URL or input
      const amount = parseFloat(route.query.amount)
      confirmResult = await portfolioStore.confirmWithdraw(amount, previewPlan.value)
    } else {
      confirmResult = await portfolioStore.confirmRebalance(previewPlan.value)
    }

    if (!confirmResult || portfolioStore.error) {
      throw new Error(portfolioStore.error || 'Execution failed to start.')
    }

    // 2. Start Live Execution
    await api.post('/trading/execute')
    
    // 3. Start Polling
    startPolling()
  } catch (err) {
    console.error("Execution failed to start", err)
    portfolioStore.error = err.message || err.response?.data?.detail || 'Execution failed.'
    isExecuting.value = false
    step.value = 'preview' // Return to preview so they see the error
  }
}

function startPolling() {
  if (pollingInterval) clearInterval(pollingInterval)
  pollingInterval = setInterval(async () => {
    try {
      const response = await api.get('/trading/execution-status')
      executionStatus.value = response.data
      
      if (response.data.status === 'completed' || response.data.status === 'stopped') {
        clearInterval(pollingInterval)
        isExecuting.value = false
        if (response.data.status === 'stopped') {
          isStopped.value = true
        }
      }
    } catch (err) {
      console.error("Failed to poll status", err)
    }
  }, 2000)
}

async function handleStop() {
  try {
    await api.post('/trading/stop')
    isStopped.value = true
  } catch (err) {
    console.error("Failed to stop execution", err)
  }
}

function goToDashboard() {
  router.push('/')
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
      
      <!-- Step 1: Input -->
      <div v-else-if="step === 'input'" class="portfolio-init">
        <div class="init-card">
          <div class="init-icon">🧠</div>
          <h1>{{ action === 'add_funds' ? 'Add Funds' : 'Initialize Portfolio' }}</h1>
          <p class="text-secondary mb-lg">
            {{ action === 'add_funds' ? 'Enter additional capital to invest.' : 'Enter initial investment capital.' }}
          </p>

          <div v-if="portfolioStore.error" class="error-message">
            {{ portfolioStore.error }}
          </div>

          <div class="input-group">
            <label for="capital-input">Amount (₹)</label>
            <input
              id="capital-input"
              v-model="inputAmount"
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
            :disabled="!inputAmount || parseFloat(inputAmount) <= 0"
            @click="handlePreview"
          >
            🚀 Preview Plan
          </button>
        </div>
      </div>

      <!-- Step 2: Optimizing (Loading) -->
      <div v-else-if="step === 'previewing'" class="loading-overlay">
        <div class="spinner" style="width:48px;height:48px;border-width:4px;"></div>
        <h2>Running PPO Portfolio Optimization...</h2>
        <p class="text-secondary">Analyzing live market data and computing optimal weights</p>
      </div>

      <!-- Step 3: Preview Plan -->
      <div v-else-if="step === 'preview'" class="portfolio-init" style="max-width: 900px; margin: 0 auto;">
        <div class="card" style="width: 100%;">
          <div v-if="portfolioStore.error" class="error-message mb-md">
            {{ portfolioStore.error }}
          </div>
          <div class="flex justify-between items-center mb-md">
            <h2>Target Allocations {{ action === 'withdraw_funds' ? '(After Withdrawal)' : '' }}</h2>
            <div class="text-secondary">Total Value: {{ formatCurrency(previewPlan?.total_capital || previewPlan?.total_value) }}</div>
          </div>
          
          <table class="data-table">
            <thead>
              <tr>
                <th style="text-transform: uppercase;">Stock</th>
                <th style="text-transform: uppercase;">Weight</th>
                <th style="text-transform: uppercase;">Target Qty</th>
                <th style="text-transform: uppercase;">Diff</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in previewPlan.allocations" :key="a.stock_symbol">
                <td class="font-bold">{{ a.stock_name }}</td>
                <td class="font-mono">{{ (a.weight * 100).toFixed(2) }}%</td>
                <td>{{ a.target_quantity }}</td>
                <td :class="a.diff > 0 ? 'text-profit' : a.diff < 0 ? 'text-loss' : ''">
                  {{ a.diff > 0 ? '+' : '' }}{{ a.diff }}
                </td>
              </tr>
            </tbody>
          </table>
          
          <div class="text-center mt-lg flex gap-md justify-center">
            <button class="btn btn-secondary btn-lg" @click="goToDashboard">Cancel</button>
            <button class="btn btn-primary btn-lg" @click="handleConfirm">⚡ Execute Algorithmic Trading</button>
          </div>
        </div>
      </div>

      <!-- Step 4: Live Trading -->
      <div v-else-if="step === 'trading'" class="portfolio-init" style="max-width: 1000px; margin: 0 auto;">
        <div class="card" style="width: 100%;">
          <div class="flex justify-between items-center mb-lg">
            <div>
              <span style="font-size:2rem;">⚡</span>
              <h2 class="inline-block ml-sm">
                {{ !isExecuting ? (isStopped ? 'Execution Stopped' : 'Trading Complete') : 'Live Trading Execution' }}
              </h2>
            </div>
            <div v-if="isExecuting">
              <button class="btn btn-danger" @click="handleStop">🛑 Stop Execution</button>
            </div>
            <div v-else>
              <button class="btn btn-primary" @click="goToDashboard">Go to Dashboard</button>
            </div>
          </div>

          <div v-if="!isExecuting && !isStopped && executionStatus?.status === 'completed'" class="success-message mb-lg p-md" style="background: rgba(46, 204, 113, 0.1); border: 1px solid var(--profit-color); border-radius: var(--radius-md);">
            <h3 class="text-profit m-0">✅ All pending orders filled</h3>
          </div>

          <div v-if="isStopped" class="error-message mb-lg p-md" style="background: rgba(231, 76, 60, 0.1); border: 1px solid var(--loss-color); border-radius: var(--radius-md);">
            <h3 class="text-loss m-0">🛑 Trading was stopped by user. Partial fills saved.</h3>
          </div>

          <div v-if="executionStatus">
            <div class="mb-md">
              <div class="flex justify-between text-sm text-secondary mb-xs">
                <span>Execution Progress</span>
                <span>Step {{ executionStatus.current_step }} / {{ executionStatus.total_steps }}</span>
              </div>
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: `${(executionStatus.current_step / executionStatus.total_steps) * 100}%` }"></div>
              </div>
            </div>

            <div v-if="executionStatus.executed_slices?.length > 0" class="mt-lg">
              <h3>Execution Log</h3>
              <table class="data-table mt-sm">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Stock</th>
                    <th>Action</th>
                    <th>Qty</th>
                    <th>Price</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(slice, index) in executionStatus.executed_slices.slice().reverse()" :key="index">
                    <td class="text-secondary text-sm">
                      {{ new Date(slice.time).toLocaleTimeString() }}
                    </td>
                    <td class="font-bold">{{ slice.stock_symbol }}</td>
                    <td :class="slice.order_type === 'BUY' ? 'text-profit' : 'text-loss'">
                      {{ slice.order_type }}
                    </td>
                    <td>{{ slice.quantity }}</td>
                    <td>{{ formatCurrency(slice.price) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="text-center p-xl text-secondary">
              Waiting for initial trades to execute...
            </div>
          </div>
          <div v-else class="text-center p-xl text-secondary">
             <div class="spinner" style="width:24px;height:24px;border-width:2px;display:inline-block;"></div>
             Starting execution engine...
          </div>
        </div>
      </div>

    </main>
  </div>
</template>

<style scoped>
.portfolio-init {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  min-height: 80vh;
  padding-top: 5vh;
}
.init-card {
  background: var(--surface-light);
  padding: var(--spacing-xl);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-color);
  width: 100%;
  max-width: 500px;
  text-align: center;
  box-shadow: var(--shadow-md);
}
.init-icon {
  font-size: 3rem;
  margin-bottom: var(--spacing-sm);
}
.progress-bar {
  width: 100%;
  height: 8px;
  background-color: var(--surface-color);
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background-color: var(--primary-color);
  transition: width 0.3s ease;
}
</style>
