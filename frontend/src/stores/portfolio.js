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

  // ── Getters ────────────────────────────────────────────────────
  const totalValue = computed(() => {
    if (!status.value) return 0
    return status.value.current_market_value + status.value.cash_balance
  })

  const holdings = computed(() => status.value?.holdings || [])

  // ── Actions ────────────────────────────────────────────────────

  async function initializePortfolio(capital) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/initialize', { capital })
      allocation.value = response.data
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to initialize portfolio.'
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
      error.value = err.response?.data?.detail || 'Failed to fetch portfolio status.'
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
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to add funds.'
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
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to withdraw funds.'
      return null
    } finally {
      loading.value = false
    }
  }

  async function rebalance() {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/portfolio/rebalance')
      rebalancePlan.value = response.data
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to rebalance.'
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
    initializePortfolio,
    fetchStatus,
    addFunds,
    withdrawFunds,
    rebalance,
  }
})
