/**
 * Demo store — manages demo mode sessions and operations.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../composables/useApi'

export const useDemoStore = defineStore('demo', () => {
  // ── State ──────────────────────────────────────────────────────
  const sessionId = ref(null)
  const status = ref(null)
  const allocation = ref(null)
  const tradingResult = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const isActive = computed(() => !!sessionId.value)

  // ── Actions ────────────────────────────────────────────────────

  async function startDemo(capital) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/demo/start', { capital })
      sessionId.value = response.data.session_id
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to start demo.'
      return null
    } finally {
      loading.value = false
    }
  }

  async function optimize() {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/demo/optimize', {
        session_id: sessionId.value,
      })
      allocation.value = response.data
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Optimization failed.'
      return null
    } finally {
      loading.value = false
    }
  }

  async function executeTrades() {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/demo/trade', {
        session_id: sessionId.value,
      })
      tradingResult.value = response.data
      // Refresh status after trading
      await fetchStatus()
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Trading simulation failed.'
      return null
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus() {
    if (!sessionId.value) return null
    try {
      const response = await api.get(`/demo/status/${sessionId.value}`)
      status.value = response.data
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to fetch demo status.'
      return null
    }
  }

  async function addFunds(amount) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/demo/add-funds', {
        session_id: sessionId.value,
        amount,
      })
      await fetchStatus()
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
      const response = await api.post('/demo/withdraw-funds', {
        session_id: sessionId.value,
        amount,
      })
      await fetchStatus()
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
      const response = await api.post('/demo/rebalance', {
        session_id: sessionId.value,
      })
      await fetchStatus()
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Rebalance failed.'
      return null
    } finally {
      loading.value = false
    }
  }

  function resetDemo() {
    sessionId.value = null
    status.value = null
    allocation.value = null
    tradingResult.value = null
    error.value = null
  }

  return {
    sessionId,
    status,
    allocation,
    tradingResult,
    loading,
    error,
    isActive,
    startDemo,
    optimize,
    executeTrades,
    fetchStatus,
    addFunds,
    withdrawFunds,
    rebalance,
    resetDemo,
  }
})
