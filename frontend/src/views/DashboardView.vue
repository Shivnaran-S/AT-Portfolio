<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { usePortfolioStore } from '../stores/portfolio'
import AppSidebar from '../components/layout/AppSidebar.vue'
import StatCard from '../components/common/StatCard.vue'
import HoldingsTable from '../components/dashboard/HoldingsTable.vue'
import Modal from '../components/common/Modal.vue'

const router = useRouter()
const authStore = useAuthStore()
const portfolioStore = usePortfolioStore()

const showFundsModal = ref(false)
const fundsAction = ref('add') // 'add' or 'withdraw'
const fundsAmount = ref('')
const fundsError = ref('')
const fundsLoading = ref(false)

// Check if user has a portfolio
onMounted(async () => {
  await authStore.fetchUser()
  if (authStore.hasPortfolio) {
    await portfolioStore.fetchStatus()
  } else {
    // Redirect to portfolio initialization
    router.push('/portfolio')
  }
})

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
    result = await portfolioStore.addFunds(amount)
  } else {
    result = await portfolioStore.withdrawFunds(amount)
  }

  if (result) {
    showFundsModal.value = false
    await portfolioStore.fetchStatus()
  } else {
    fundsError.value = portfolioStore.error || 'Operation failed.'
  }
  fundsLoading.value = false
}

async function handleRebalance() {
  const result = await portfolioStore.rebalance()
  if (result) {
    router.push('/trading')
  }
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
