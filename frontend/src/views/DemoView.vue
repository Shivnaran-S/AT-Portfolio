<script setup>
import { ref, computed } from 'vue'
import { useDemoStore } from '../stores/demo'
import StatCard from '../components/common/StatCard.vue'
import HoldingsTable from '../components/dashboard/HoldingsTable.vue'
import Modal from '../components/common/Modal.vue'

const demoStore = useDemoStore()

const capital = ref('500000')
const step = ref('start') // 'start' | 'optimizing' | 'trading' | 'dashboard'

const showFundsModal = ref(false)
const fundsAction = ref('add')
const fundsAmount = ref('')
const fundsError = ref('')

async function startDemo() {
  const amount = parseFloat(capital.value)
  if (!amount || amount <= 0) return

  const result = await demoStore.startDemo(amount)
  if (result) {
    step.value = 'optimizing'
    await runOptimization()
  }
}

async function runOptimization() {
  step.value = 'optimizing'
  await demoStore.optimize()
}

async function runTrading() {
  step.value = 'trading'
  const result = await demoStore.executeTrades()
  if (result) {
    step.value = 'dashboard'
  }
}

function openFundsModal(action) {
  fundsAction.value = action
  fundsAmount.value = ''
  fundsError.value = ''
  showFundsModal.value = true
}

async function handleFunds() {
  const amount = parseFloat(fundsAmount.value)
  if (!amount || amount <= 0) {
    fundsError.value = 'Enter a valid amount.'
    return
  }

  let result
  if (fundsAction.value === 'add') {
    result = await demoStore.addFunds(amount)
  } else {
    result = await demoStore.withdrawFunds(amount)
  }

  if (result) {
    showFundsModal.value = false
  } else {
    fundsError.value = demoStore.error || 'Operation failed.'
  }
}

async function handleRebalance() {
  step.value = 'trading'
  await demoStore.rebalance()
  step.value = 'dashboard'
}

function resetDemo() {
  demoStore.resetDemo()
  step.value = 'start'
}

function formatCurrency(value) {
  if (value === null || value === undefined) return '₹0.00'
  return '₹' + Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatPercent(value) {
  if (!value) return '0.00%'
  return (value > 0 ? '+' : '') + value.toFixed(2) + '%'
}

const status = computed(() => demoStore.status)
</script>

<template>
  <div class="demo-page">
    <!-- Demo Badge -->
    <div class="demo-badge-bar">
      <span class="badge badge-demo">🎮 DEMO MODE</span>
      <span class="text-secondary" style="font-size:var(--font-size-sm);">
        Simulated market environment — no real money involved
      </span>
      <button v-if="step !== 'start'" class="btn btn-sm btn-secondary" @click="resetDemo">
        Reset Demo
      </button>
    </div>

    <!-- Step 1: Start Demo -->
    <div v-if="step === 'start'" class="demo-start">
      <div class="init-card">
        <div style="font-size:3rem;">🎮</div>
        <h1>Demo Mode</h1>
        <p class="text-secondary mb-lg">
          Experience PPO-powered portfolio optimization and algorithmic trading
          in a simulated market. No account needed.
        </p>

        <div v-if="demoStore.error" class="error-message">{{ demoStore.error }}</div>

        <div class="input-group">
          <label for="demo-capital">Investment Capital (₹)</label>
          <input
            id="demo-capital"
            v-model="capital"
            type="number"
            class="input"
            placeholder="e.g., 500000"
            min="10000"
            max="1000000"
            style="font-size:var(--font-size-xl);text-align:center;"
          />
        </div>

        <button
          class="btn btn-gold btn-lg w-full"
          :disabled="demoStore.loading"
          @click="startDemo"
        >
          🚀 Start Demo
        </button>

        <p class="text-muted mt-md" style="font-size:var(--font-size-xs);">
          Maximum investment: ₹10,00,000
        </p>
      </div>
    </div>

    <!-- Step 2: Optimizing -->
    <div v-else-if="step === 'optimizing'" class="loading-overlay">
      <div v-if="!demoStore.allocation">
        <div class="spinner" style="width:48px;height:48px;border-width:4px;"></div>
        <h2>Running PPO Portfolio Optimization...</h2>
        <p class="text-secondary">Analyzing stocks and generating optimal weights</p>
      </div>

      <div v-if="demoStore.allocation" class="mt-lg">
        <div class="card" style="max-width:800px;margin:0 auto;">
          <h3 class="mb-md">Target Allocations</h3>
          <table class="data-table">
            <thead>
              <tr>
                <th>Stock</th>
                <th>Weight</th>
                <th>Target Qty</th>
                <th>Diff</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in demoStore.allocation.allocations" :key="a.stock_symbol">
                <td class="font-bold">{{ a.stock_name }}</td>
                <td class="font-mono">{{ (a.weight * 100).toFixed(2) }}%</td>
                <td>{{ a.target_quantity }}</td>
                <td :class="a.diff > 0 ? 'text-profit' : a.diff < 0 ? 'text-loss' : ''">
                  {{ a.diff > 0 ? '+' : '' }}{{ a.diff }}
                </td>
              </tr>
            </tbody>
          </table>
          <div class="text-center mt-lg">
            <button class="btn btn-primary btn-lg" @click="runTrading">
              ⚡ Execute Algorithmic Trading
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Step 3: Trading Simulation -->
    <div v-else-if="step === 'trading'" class="loading-overlay">
      <div class="spinner" style="width:48px;height:48px;border-width:4px;"></div>
      <h2>Executing Algorithmic Trades...</h2>
      <p class="text-secondary">PPO agent is slicing and timing orders for optimal execution</p>
    </div>

    <!-- Step 4: Dashboard -->
    <div v-else-if="step === 'dashboard' && status" class="demo-dashboard">
      <div class="page-header flex justify-between items-center">
        <div>
          <h1>Demo Dashboard</h1>
          <p>Your simulated portfolio results</p>
        </div>
        <div class="flex gap-md">
          <button class="btn btn-secondary" @click="openFundsModal('add')">💰 Add Funds</button>
          <button class="btn btn-secondary" @click="openFundsModal('withdraw')">💸 Withdraw</button>
          <button class="btn btn-primary" @click="handleRebalance">⚖️ Rebalance</button>
          <button class="btn btn-gold" @click="runOptimization">🧠 Re-Optimize</button>
        </div>
      </div>

      <div class="stats-grid">
        <StatCard
          label="Portfolio Value"
          :value="formatCurrency(status.current_market_value + status.cash_balance)"
          :change="formatPercent(status.total_profit_loss_percent)"
          :is-positive="status.total_profit_loss >= 0"
          icon="📊"
        />
        <StatCard label="Total Invested" :value="formatCurrency(status.total_invested)" icon="💼" />
        <StatCard label="Cash Balance" :value="formatCurrency(status.cash_balance)" icon="🏦" />
        <StatCard
          label="Total P&L"
          :value="formatCurrency(status.total_profit_loss)"
          :is-positive="status.total_profit_loss >= 0"
          icon="📈"
        />
        <StatCard
          label="Realized P&L"
          :value="formatCurrency(status.realized_profit_loss)"
          :is-positive="status.realized_profit_loss >= 0"
          icon="✅"
        />
        <StatCard
          label="Unrealized P&L"
          :value="formatCurrency(status.unrealized_profit_loss)"
          :is-positive="status.unrealized_profit_loss >= 0"
          icon="⏳"
        />
      </div>

      <div class="card">
        <h2 style="margin-bottom:var(--space-lg);font-size:var(--font-size-xl);">Holdings</h2>
        <HoldingsTable :holdings="status.holdings" />
      </div>

      <!-- Trading Results -->
      <div v-if="demoStore.tradingResult" class="card mt-lg">
        <h2 style="margin-bottom:var(--space-lg);font-size:var(--font-size-xl);">
          Last Trading Session — {{ demoStore.tradingResult.orders_executed }} orders executed
        </h2>
        <div v-for="order in demoStore.tradingResult.execution_report" :key="order.stock_symbol" class="execution-card mb-md">
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-md">
              <span class="badge" :class="order.order_type === 'BUY' ? 'badge-success' : 'badge-danger'">
                {{ order.order_type }}
              </span>
              <strong>{{ order.stock_symbol }}</strong>
            </div>
            <span>{{ order.filled_quantity }} shares in {{ order.slices.length }} slices</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Funds Modal -->
    <Modal v-if="showFundsModal" @close="showFundsModal = false">
      <h2>{{ fundsAction === 'add' ? '💰 Add Funds' : '💸 Withdraw Funds' }}</h2>
      <p class="text-secondary mb-md" style="font-size:var(--font-size-sm);">
        <template v-if="fundsAction === 'add'">
          Deposit additional capital. Demo limit: ₹10,00,000.
        </template>
        <template v-else>
          Maximum withdrawal: current market value of your holdings
          ({{ status ? formatCurrency(status.current_market_value) : '₹0.00' }}).
        </template>
      </p>
      <div v-if="fundsError" class="error-message">{{ fundsError }}</div>
      <div class="input-group">
        <label for="demo-funds">Amount (₹)</label>
        <input
          id="demo-funds"
          v-model="fundsAmount"
          type="number"
          class="input"
          placeholder="Enter amount"
          min="1"
          :max="fundsAction === 'withdraw' && status ? status.current_market_value : undefined"
        />
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" @click="showFundsModal = false">Cancel</button>
        <button
          class="btn"
          :class="fundsAction === 'add' ? 'btn-primary' : 'btn-danger'"
          @click="handleFunds"
        >{{ fundsAction === 'add' ? 'Deposit' : 'Withdraw' }}</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.demo-page {
  min-height: 100vh;
  background: var(--bg-primary);
  padding: var(--space-lg);
}

.demo-badge-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-xl);
}

.demo-start {
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

.init-card h1 {
  font-size: var(--font-size-2xl);
  margin: var(--space-md) 0 var(--space-sm);
}

.demo-dashboard {
  max-width: 1400px;
  margin: 0 auto;
}

.execution-card {
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: var(--space-md);
}
</style>
