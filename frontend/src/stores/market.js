/**
 * Market store — manages stock universe and price data.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../composables/useApi'

export const useMarketStore = defineStore('market', () => {
  const stocks = ref([])
  const prices = ref([])
  const lastUpdated = ref(null)
  const loading = ref(false)

  async function fetchStocks() {
    loading.value = true
    try {
      const response = await api.get('/market/stocks')
      stocks.value = response.data
    } catch (err) {
      console.error('Failed to fetch stocks:', err)
    } finally {
      loading.value = false
    }
  }

  async function fetchPrices() {
    loading.value = true
    try {
      const response = await api.get('/market/prices')
      prices.value = response.data.prices
      lastUpdated.value = response.data.last_updated
    } catch (err) {
      console.error('Failed to fetch prices:', err)
    } finally {
      loading.value = false
    }
  }

  return {
    stocks,
    prices,
    lastUpdated,
    loading,
    fetchStocks,
    fetchPrices,
  }
})
