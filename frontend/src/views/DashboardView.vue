<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { usePortfolioStore } from '../stores/portfolio'
import AppSidebar from '../components/layout/AppSidebar.vue'
import StatCard from '../components/common/StatCard.vue'
import HoldingsTable from '../components/dashboard/HoldingsTable.vue'
import Modal from '../components/common/Modal.vue'

import api from '../composables/useApi'

const router = useRouter()
const authStore = useAuthStore()
const portfolioStore = usePortfolioStore()

const showFundsModal = ref(false)
const fundsAction = ref('add') // 'add' or 'withdraw'
const fundsAmount = ref('')
const fundsError = ref('')
const fundsLoading = ref(false)

const orders = ref([])
const expandedOrders = ref(new Set())

// Check if user has a portfolio
onMounted(async () => {
  await authStore.fetchUser()
  if (authStore.hasPortfolio) {
    await portfolioStore.fetchStatus()
    await loadOrders()
  } else {
    // Redirect to portfolio initialization
    router.push('/portfolio')
  }
})

async function loadOrders() {
  try {
    const response = await api.get('/trading/orders')
    // Filter to only show orders that have been executed at least partially
    orders.value = response.data.filter(o => o.slices && o.slices.length > 0)
  } catch (err) {
    console.error('Failed to load orders:', err)
  }
}

function toggleOrder(symbol) {
  if (expandedOrders.value.has(symbol)) {
    expandedOrders.value.delete(symbol)
  } else {
    expandedOrders.value.add(symbol)
  }
}

const status = computed(() => portfolioStore.status)

function formatCurrency(value) {
  if (value === null || value === undefined) return '₹0.00'
  return '₹' + Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatPercent(value) {
  if (!value) return '0.00%'
  const sign = value > 0 ? '+' : ''
  return sign + value.toFixed(2) + '%'
}

function formatDateTime(isoString) {
  if (!isoString) return '—'
  const date = new Date(isoString)
  return date.toLocaleString('en-IN', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
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
    fundsError.value = 'Please enter a valid amount.'
    return
  }

  fundsLoading.value = true
  fundsError.value = ''

  let result
  if (fundsAction.value === 'add') {
    showFundsModal.value = false
    router.push(`/portfolio?action=add_funds&amount=${amount}`)
    return
  } else {
    if (amount > status.value.cash_balance) {
      showFundsModal.value = false
      router.push(`/portfolio?action=withdraw_funds&amount=${amount}`)
      return
    } else {
      result = await portfolioStore.withdrawFunds(amount)
    }
  }

  if (result) {
    showFundsModal.value = false
    await portfolioStore.fetchStatus()
  } else {
    fundsError.value = portfolioStore.error || 'Operation failed.'
  }
  fundsLoading.value = false
}

function handleRebalance() {
  router.push('/portfolio?action=rebalance')
}
</script>

<template>
  <div class="app-layout">
    <AppSidebar />

    <main class="main-content">
      <!-- Loading State -->
      <div v-if="portfolioStore.loading && !status" class="loading-overlay">
        <div class="spinner"></div>
        <p>Loading your portfolio...</p>
      </div>

      <!-- Dashboard Content -->
      <div v-else-if="status">
        <div class="page-header flex justify-between items-center">
          <div>
            <h1>Dashboard</h1>
            <p>Your portfolio at a glance</p>
          </div>
          <div class="flex gap-md">
            <button class="btn btn-secondary" @click="openFundsModal('add')">
              💰 Add Funds
            </button>
            <button class="btn btn-secondary" @click="openFundsModal('withdraw')">
              💸 Withdraw
            </button>
            <button class="btn btn-primary" @click="handleRebalance">
              ⚖️ Rebalance
            </button>
          </div>
        </div>

        <!-- Top Stat Cards -->
        <div class="stats-grid">
          <StatCard
            label="Portfolio Value"
            :value="formatCurrency(status.current_market_value + status.cash_balance)"
            :change="formatPercent(status.total_profit_loss_percent)"
            :is-positive="status.total_profit_loss >= 0"
            icon="📊"
          />
          <StatCard
            label="Total Invested"
            :value="formatCurrency(status.total_invested)"
            icon="💼"
          />
          <StatCard
            label="Cash Balance"
            :value="formatCurrency(status.cash_balance)"
            icon="🏦"
          />
          <StatCard
            label="Total P&L"
            :value="formatCurrency(status.total_profit_loss)"
            :change="formatPercent(status.total_profit_loss_percent)"
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

        <!-- Holdings Table -->
        <div class="card">
          <h2 style="margin-bottom: var(--space-lg); font-size: var(--font-size-xl);">
            Holdings
          </h2>
          <HoldingsTable :holdings="status.holdings" />
        </div>

        <!-- Trading Results -->
        <div v-if="orders.length > 0" class="card mt-lg">
          <h2 style="margin-bottom:var(--space-lg);font-size:var(--font-size-xl);">
            Trade Execution History
          </h2>
          <div v-for="order in orders" :key="order.id" class="execution-card mb-md"
            @click="toggleOrder(order.id)"
            style="cursor:pointer;"
          >
            <div class="flex justify-between items-center">
              <div class="flex items-center gap-md">
                <span class="badge" :class="order.order_type === 'BUY' ? 'badge-success' : 'badge-danger'">
                  {{ order.order_type }}
                </span>
                <strong>{{ order.stock_symbol }}</strong>
              </div>
              <div class="flex items-center gap-md">
                <span>{{ order.filled_quantity }} / {{ order.total_quantity }} shares filled ({{ order.slices?.length || 0 }} slices)</span>
                <span class="expand-arrow" :class="{ expanded: expandedOrders.has(order.id) }">▸</span>
              </div>
            </div>
            
            <!-- Expandable slice details -->
            <div v-if="expandedOrders.has(order.id)" class="slice-details mt-sm">
              <table class="slice-table">
                <thead>
                  <tr>
                    <th>Date & Time</th>
                    <th>Quantity</th>
                    <th>Execution Price</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="slice in order.slices" :key="slice.id">
                    <td class="text-secondary">{{ formatDateTime(slice.executed_at) }}</td>
                    <td>{{ slice.quantity }}</td>
                    <td>{{ formatCurrency(slice.price) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- No Portfolio State -->
      <div v-else class="loading-overlay">
        <p>No portfolio data available.</p>
        <router-link to="/portfolio" class="btn btn-primary">
          Initialize Portfolio
        </router-link>
      </div>
    </main>

    <!-- Add/Withdraw Funds Modal -->
    <Modal v-if="showFundsModal" @close="showFundsModal = false">
      <h2>{{ fundsAction === 'add' ? '💰 Add Funds' : '💸 Withdraw Funds' }}</h2>
      <p class="text-secondary mb-lg">
        <template v-if="fundsAction === 'add'">
          Deposit additional capital. Maximum total investment: ₹1,00,00,000.
        </template>
        <template v-else>
          Withdraw funds. Maximum withdrawal: current market value of your holdings
          ({{ formatCurrency(status.current_market_value) }}).
        </template>
      </p>

      <div v-if="fundsError" class="error-message">{{ fundsError }}</div>

      <div class="input-group">
        <label for="funds-amount">Amount (₹)</label>
        <input
          id="funds-amount"
          v-model="fundsAmount"
          type="number"
          class="input"
          placeholder="Enter amount"
          min="1"
          :max="fundsAction === 'withdraw' ? status.current_market_value : undefined"
          step="1000"
        />
      </div>

      <div class="modal-actions">
        <button class="btn btn-secondary" @click="showFundsModal = false">Cancel</button>
        <button
          class="btn"
          :class="fundsAction === 'add' ? 'btn-primary' : 'btn-danger'"
          :disabled="fundsLoading"
          @click="handleFunds"
        >
          {{ fundsLoading ? 'Processing...' : (fundsAction === 'add' ? 'Deposit' : 'Withdraw') }}
        </button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
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
.expand-arrow {
  display: inline-block;
  transition: transform 0.2s ease;
  font-size: 1.2rem;
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
  border-collapse: collapse;
}
.slice-table th,
.slice-table td {
  padding: var(--space-sm);
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}
.slice-table th {
  color: var(--text-secondary);
  font-weight: 500;
  font-size: var(--font-size-sm);
}
.slice-table tr:last-child td {
  border-bottom: none;
}
</style>
