/**
 * Auth store — manages user authentication state.
 *
 * Handles login, signup, token storage, and current user info.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../composables/useApi'

export const useAuthStore = defineStore('auth', () => {
  // ── State ──────────────────────────────────────────────────────
  const user = ref(null)
  const token = ref(localStorage.getItem('token') || null)
  const loading = ref(false)
  const error = ref(null)

  // ── Getters ────────────────────────────────────────────────────
  const isAuthenticated = computed(() => !!token.value)
  const hasPortfolio = computed(() => user.value?.has_portfolio || false)

  // ── Actions ────────────────────────────────────────────────────

  async function signup(username, password) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/auth/signup', { username, password })
      user.value = response.data
      return true
    } catch (err) {
      error.value = err.response?.data?.detail || 'Signup failed.'
      return false
    } finally {
      loading.value = false
    }
  }

  async function login(username, password) {
    loading.value = true
    error.value = null
    try {
      const response = await api.post('/auth/login', { username, password })
      token.value = response.data.access_token
      localStorage.setItem('token', token.value)

      // Fetch user profile
      await fetchUser()
      return true
    } catch (err) {
      error.value = err.response?.data?.detail || 'Login failed.'
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      const response = await api.get('/auth/me')
      user.value = response.data
    } catch (err) {
      // Token might be expired
      logout()
    }
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('token')
  }

  return {
    user,
    token,
    loading,
    error,
    isAuthenticated,
    hasPortfolio,
    signup,
    login,
    fetchUser,
    logout,
  }
})
