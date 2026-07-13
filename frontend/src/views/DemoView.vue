<script setup>
import { ref, computed, onUnmounted, watch } from 'vue'
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

// Trade history expansion state
const expandedOrders = ref(new Set())

function toggleOrder(symbol) {
  if (expandedOrders.value.has(symbol)) {
    expandedOrders.value.delete(symbol)
  } else {
    expandedOrders.value.add(symbol)
  }
}

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
  await demoStore.executeTrades()
}

// Watch for simulation completion — don't auto-navigate, show completion banner instead
const completionChecker = setInterval(() => {
  // Only auto-navigate if not in trading view (for rebalance from dashboard)
}, 500)

onUnmounted(() => {
  clearInterval(completionChecker)
})

function goToDashboard() {
  step.value = 'dashboard'
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
    // If withdrawal started a sell simulation, transition to trading view
    if (result.status === 'started') {
      step.value = 'trading'
    }
  } else {
    fundsError.value = demoStore.error || 'Operation failed.'
  }
}

async function handleRebalance() {
  step.value = 'trading'
  await demoStore.rebalance()
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

const status = computed(() => demoStore.status)
const sim = computed(() => demoStore.simulationStatus)
const isCompleted = computed(() => sim.value?.status === 'completed')
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

    <!-- Step 3: Trading Simulation (Live Progress) -->
    <div v-else-if="step === 'trading'" class="simulation-view">
      <div class="sim-card">
        <div class="sim-header">
          <span style="font-size:2rem;">⚡</span>
          <h2>{{ isCompleted ? 'Trading Complete' : 'Trading Simulation' }}</h2>
          <p class="text-secondary">
            <template v-if="isCompleted">
              All trades have been executed successfully.
            </template>
            <template v-else>
              Simulating a full trading day in
              {{ sim?.duration_seconds ? Math.round(sim.duration_seconds / 60) : '...' }} minutes
            </template>
          </p>
        </div>

        <!-- Completion Banner -->
        <div v-if="isCompleted" class="completion-banner">
          <div class="completion-icon">✅</div>
          <h3>All Shares Purchased</h3>
          <div class="completion-stats">
            <div class="stat-pill">
              <span class="stat-label">Trades</span>
              <span class="stat-value">{{ sim?.trades_executed || 0 }}</span>
            </div>
            <div class="stat-pill">
              <span class="stat-label">Steps Used</span>
              <span class="stat-value">{{ sim?.current_step || 0 }} / {{ sim?.total_steps || 0 }}</span>
            </div>
            <div class="stat-pill">
              <span class="stat-label">Time</span>
              <span class="stat-value">{{ sim?.elapsed_seconds ? Math.round(sim.elapsed_seconds) : 0 }}s</span>
            </div>
            <div class="stat-pill">
              <span class="stat-label">Stocks</span>
              <span class="stat-value">{{ sim?.execution_report?.length || 0 }}</span>
            </div>
          </div>

          <!-- Execution Summary -->
          <div v-if="sim?.execution_report?.length" class="execution-summary mt-lg">
            <h4 class="mb-md">Execution Summary</h4>
            <div
              v-for="order in sim.execution_report"
              :key="order.stock_symbol"
              class="execution-card mb-sm"
              @click="toggleOrder(order.stock_symbol)"
              style="cursor:pointer;"
            >
              <div class="flex justify-between items-center">
                <div class="flex items-center gap-md">
                  <span class="badge badge-sm" :class="order.order_type === 'BUY' ? 'badge-success' : 'badge-danger'">
                    {{ order.order_type }}
                  </span>
                  <strong>{{ order.stock_name || order.stock_symbol }}</strong>
                </div>
                <div class="flex items-center gap-md">
                  <span class="font-mono">{{ order.filled_quantity }} shares · {{ order.slices?.length || 0 }} slices</span>
                  <span class="expand-arrow" :class="{ expanded: expandedOrders.has(order.stock_symbol) }">▸</span>
                </div>
              </div>
              <!-- Expandable slice details -->
              <div v-if="expandedOrders.has(order.stock_symbol)" class="slice-details mt-sm">
                <table class="slice-table">
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Time</th>
                      <th>Shares</th>
                      <th>Price</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(slice, idx) in order.slices" :key="idx">
                      <td class="font-mono">{{ slice.step }}</td>
                      <td>{{ formatTime(slice.time) }}</td>
                      <td class="font-mono font-bold">{{ slice.quantity }}</td>
                      <td class="font-mono">{{ formatCurrency(slice.price) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <button class="btn btn-gold btn-lg w-full mt-lg" @click="goToDashboard">
            📊 Go to Dashboard
          </button>
        </div>

        <!-- Progress Bar (only when running) -->
        <div v-if="!isCompleted" class="progress-section">
          <div class="progress-info">
            <span class="font-mono">
              Step {{ sim?.current_step || 0 }} / {{ sim?.total_steps || '...' }}
              · {{ sim?.trades_executed || 0 }} trades
            </span>
            <span class="font-mono font-bold">
              {{ sim?.progress_percent?.toFixed(1) || '0.0' }}%
            </span>
          </div>
          <div class="progress-bar-track">
            <div
              class="progress-bar-fill"
              :style="{ width: (sim?.progress_percent || 0) + '%' }"
            ></div>
          </div>
          <div class="progress-info mt-sm">
            <span class="text-muted">
              Elapsed: {{ sim?.elapsed_seconds ? Math.round(sim.elapsed_seconds) : 0 }}s
            </span>
            <span class="text-muted">
              Total: {{ sim?.duration_seconds || '...' }}s
            </span>
          </div>
        </div>

        <!-- Live Trade Feed (only when running) -->
        <div v-if="!isCompleted" class="trade-feed">
          <h3 class="mb-md">Live Trade Feed</h3>
          <div v-if="!sim?.executed_slices?.length" class="text-center text-muted" style="padding:var(--space-lg);">
            <div class="spinner" style="width:24px;height:24px;border-width:2px;margin:0 auto;"></div>
            <p class="mt-md">Agent is observing prices and deciding when to trade...</p>
          </div>
          <div v-else class="feed-list">
            <div
              v-for="(slice, idx) in [...(sim?.executed_slices || [])].reverse()"
              :key="idx"
              class="feed-item"
              :class="{ 'feed-item-new': idx === 0 }"
            >
              <span
                class="badge badge-sm"
                :class="slice.order_type === 'BUY' ? 'badge-success' : 'badge-danger'"
              >{{ slice.order_type }}</span>
              <strong>{{ slice.stock_name || slice.stock_symbol }}</strong>
              <span class="font-mono">{{ slice.quantity }} shares</span>
              <span class="font-mono text-secondary">@ {{ formatCurrency(slice.price) }}</span>
              <span class="text-muted" style="font-size:var(--font-size-xs);">
                {{ formatTime(slice.time) }}
              </span>
            </div>
          </div>
        </div>
      </div>
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
        <div v-for="order in demoStore.tradingResult.execution_report" :key="order.stock_symbol" class="execution-card mb-md"
          @click="toggleOrder('dash-' + order.stock_symbol)"
          style="cursor:pointer;"
        >
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-md">
              <span class="badge" :class="order.order_type === 'BUY' ? 'badge-success' : 'badge-danger'">
                {{ order.order_type }}
              </span>
              <strong>{{ order.stock_name || order.stock_symbol }}</strong>
            </div>
            <div class="flex items-center gap-md">
              <span>{{ order.filled_quantity }} shares in {{ order.slices?.length || 0 }} slices</span>
              <span class="expand-arrow" :class="{ expanded: expandedOrders.has('dash-' + order.stock_symbol) }">▸</span>
            </div>
          </div>
          <!-- Expandable slice details -->
          <div v-if="expandedOrders.has('dash-' + order.stock_symbol)" class="slice-details mt-sm">
            <table class="slice-table">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Time</th>
                  <th>Shares</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(slice, idx) in order.slices" :key="idx">
                  <td class="font-mono">{{ slice.step }}</td>
                  <td>{{ formatTime(slice.time) }}</td>
                  <td class="font-mono font-bold">{{ slice.quantity }}</td>
                  <td class="font-mono">{{ formatCurrency(slice.price) }}</td>
                </tr>
              </tbody>
            </table>
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
          Shares will be sold to cover the withdrawal amount.
          Maximum: current market value of your holdings
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
  transition: background 0.2s ease;
}

.execution-card:hover {
  background: var(--bg-glass-hover, rgba(255,255,255,0.05));
}

/* ── Completion Banner ──────────────────────────────────────────── */

.completion-banner {
  text-align: center;
  padding: var(--space-lg);
  background: rgba(16, 185, 129, 0.05);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-lg);
}

.completion-icon {
  font-size: 3rem;
  margin-bottom: var(--space-sm);
}

.completion-banner h3 {
  font-size: var(--font-size-xl);
  color: var(--accent-primary);
  margin-bottom: var(--space-md);
}

.completion-stats {
  display: flex;
  justify-content: center;
  gap: var(--space-lg);
  flex-wrap: wrap;
}

.stat-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  min-width: 80px;
}

.stat-pill .stat-label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-pill .stat-value {
  font-size: var(--font-size-lg);
  font-weight: 700;
  font-family: var(--font-mono, monospace);
}

/* ── Expandable Slice Details ───────────────────────────────────── */

.expand-arrow {
  transition: transform 0.2s ease;
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.slice-details {
  border-top: 1px solid var(--border-color);
  padding-top: var(--space-sm);
}

.slice-table {
  width: 100%;
  font-size: var(--font-size-sm);
  border-collapse: collapse;
}

.slice-table th {
  text-align: left;
  padding: var(--space-xs) var(--space-sm);
  color: var(--text-muted);
  font-weight: 500;
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-color);
}

.slice-table td {
  padding: var(--space-xs) var(--space-sm);
  border-bottom: 1px solid rgba(255,255,255,0.03);
}

.execution-summary {
  text-align: left;
}

.execution-summary h4 {
  font-size: var(--font-size-md);
  color: var(--text-secondary);
}

/* ── Simulation Progress ────────────────────────────────────────── */

.simulation-view {
  display: flex;
  justify-content: center;
  padding-top: var(--space-xl);
}

.sim-card {
  max-width: 700px;
  width: 100%;
  background: var(--bg-card);
  backdrop-filter: blur(20px);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  padding: var(--space-2xl);
}

.sim-header {
  text-align: center;
  margin-bottom: var(--space-xl);
}

.sim-header h2 {
  font-size: var(--font-size-xl);
  margin: var(--space-sm) 0 var(--space-xs);
}

.progress-section {
  margin-bottom: var(--space-xl);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  font-size: var(--font-size-sm);
  margin-bottom: var(--space-xs);
}

.progress-bar-track {
  width: 100%;
  height: 12px;
  background: var(--bg-glass);
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary, #60a5fa));
  border-radius: 6px;
  transition: width 0.5s ease;
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
}

.trade-feed {
  max-height: 350px;
  overflow-y: auto;
}

.trade-feed h3 {
  font-size: var(--font-size-lg);
  position: sticky;
  top: 0;
  background: var(--bg-card);
  padding-bottom: var(--space-sm);
  z-index: 1;
}

.feed-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.feed-item {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  transition: all 0.3s ease;
}

.feed-item-new {
  animation: feedPulse 0.6s ease;
}

@keyframes feedPulse {
  0% {
    background: rgba(16, 185, 129, 0.15);
    transform: translateX(-4px);
  }
  100% {
    background: var(--bg-glass);
    transform: translateX(0);
  }
}

.badge-sm {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
}
</style>
