/**
 * Portfolio store — manages portfolio data, status, and operations.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../composables/useApi'

export const usePortfolioStore = defineStore('portfolio', () => {
  // ── State ──────────────────────────────────────────────────────
  const status = ref(null)
  const allocation = ref(null)
  const rebalancePlan = ref(null)
  const loading = ref(false)
  const error = ref(null)

  function formatError(err, defaultMsg) {
    const detail = err.response?.data?.detail
    if (Array.isArray(detail)) {
      // Map FastAPI validation errors to a cleaner string
      const msgs = detail.map(d => {
        const field = d.loc && d.loc.length > 1 ? d.loc[d.loc.length - 1] : 'field'
        return `${field}: ${d.msg}`
      })
      return msgs.join(', ') || defaultMsg
    }
    return detail || defaultMsg
  }

  // ── Getters ────────────────────────────────────────────────────
  const totalValue = computed(() => {
    if (!status.value) return 0
    return status.value.current_market_value + status.value.cash_balance
  })

  const holdings = computed(() => status.value?.holdings || [])

  // ── Actions ────────────────────────────────────────────────────

  async function previewInitialize(capital) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/initialize-preview', { capital })
      allocation.value = response.data
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to preview initialization.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function confirmInitialize(plan) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/initialize', plan)
      allocation.value = response.data
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to initialize portfolio.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus() {
    loading.value = true
    error.value = null
    try {
      const response = await api.get('/portfolio/status')
      status.value = response.data
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to fetch portfolio status.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function addFunds(amount) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/add-funds', { amount })
      await fetchStatus()
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to add funds.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function previewWithdraw(amount) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/withdraw-preview', { amount })
      rebalancePlan.value = response.data
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to preview withdrawal.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function confirmWithdraw(amount, plan) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/withdraw-funds', { plan, amount })
      rebalancePlan.value = null
      await fetchStatus()
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to confirm withdrawal.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function withdrawFunds(amount) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/withdraw-funds', { amount })
      await fetchStatus()
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to withdraw funds.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function previewRebalance() {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/rebalance-preview')
      rebalancePlan.value = response.data
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to preview rebalance.')
      return null
    } finally {
      loading.value = false
    }
  }

  async function confirmRebalance(plan) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/rebalance', plan)
      rebalancePlan.value = null
      await fetchStatus()
      return response.data
    } catch (err) {
      error.value = formatError(err, 'Failed to confirm rebalance.')
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    status,
    allocation,
    rebalancePlan,
    loading,
    error,
    totalValue,
    holdings,
    previewInitialize,
    confirmInitialize,
    fetchStatus,
    addFunds,
    withdrawFunds,
    previewWithdraw,
    confirmWithdraw,
    previewRebalance,
    confirmRebalance,
  }
})
