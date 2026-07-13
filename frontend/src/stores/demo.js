/**
 * Demo store — manages demo mode sessions and operations.
 *
 * Supports compressed trading simulation with polling-based progress tracking.
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
  const simulationStatus = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const isActive = computed(() => !!sessionId.value)
  const simulationRunning = computed(
    () => simulationStatus.value?.status === 'running'
  )

  let pollTimer = null

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
    simulationStatus.value = null
    tradingResult.value = null
    try {
      const response = await api.post('/demo/trade', {
        session_id: sessionId.value,
      })

      if (response.data.status === 'completed') {
        // No trades needed
        tradingResult.value = response.data
        await fetchStatus()
        loading.value = false
        return response.data
      }

      // Simulation started — begin polling
      simulationStatus.value = {
        status: 'running',
        total_steps: response.data.total_steps,
        current_step: 0,
        trades_executed: 0,
        progress_percent: 0,
        elapsed_seconds: 0,
        duration_seconds: response.data.duration_seconds,
        executed_slices: [],
      }

      startPolling()
      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Trading simulation failed.'
      loading.value = false
      return null
    }
  }

  function startPolling() {
    stopPolling()
    pollTimer = setInterval(async () => {
      try {
        const response = await api.get(
          `/demo/simulation-status/${sessionId.value}`
        )
        simulationStatus.value = response.data

        if (response.data.status === 'completed') {
          stopPolling()
          tradingResult.value = {
            orders_executed: response.data.orders_executed,
            execution_report: response.data.execution_report,
          }
          await fetchStatus()
          loading.value = false
        }
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 2000) // Poll every 2 seconds
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
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
    simulationStatus.value = null
    tradingResult.value = null
    try {
      const response = await api.post('/demo/withdraw-funds', {
        session_id: sessionId.value,
        amount,
      })

      // If withdrawal triggers a sell simulation, start polling
      if (response.data.status === 'started') {
        simulationStatus.value = {
          status: 'running',
          total_steps: response.data.total_steps,
          current_step: 0,
          trades_executed: 0,
          progress_percent: 0,
          elapsed_seconds: 0,
          duration_seconds: response.data.duration_seconds,
          executed_slices: [],
        }
        startPolling()
      } else {
        // Instant withdrawal (from cash balance only)
        await fetchStatus()
        loading.value = false
      }

      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Failed to withdraw funds.'
      loading.value = false
      return null
    }
  }

  async function rebalance() {
    loading.value = true
    error.value = null
    simulationStatus.value = null
    tradingResult.value = null
    try {
      const response = await api.post('/demo/rebalance', {
        session_id: sessionId.value,
      })

      // Start polling for simulation progress
      if (response.data.trading?.status === 'started') {
        simulationStatus.value = {
          status: 'running',
          total_steps: response.data.trading.total_steps,
          current_step: 0,
          trades_executed: 0,
          progress_percent: 0,
          elapsed_seconds: 0,
          duration_seconds: response.data.trading.duration_seconds,
          executed_slices: [],
        }
        startPolling()
      } else {
        await fetchStatus()
        loading.value = false
      }

      return response.data
    } catch (err) {
      error.value = err.response?.data?.detail || 'Rebalance failed.'
      loading.value = false
      return null
    }
  }

  function resetDemo() {
    stopPolling()
    sessionId.value = null
    status.value = null
    allocation.value = null
    tradingResult.value = null
    simulationStatus.value = null
    error.value = null
  }

  return {
    sessionId,
    status,
    allocation,
    tradingResult,
    simulationStatus,
    loading,
    error,
    isActive,
    simulationRunning,
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
