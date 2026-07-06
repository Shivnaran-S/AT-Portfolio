/**
 * Composable for making API requests to the backend.
 *
 * Wraps axios with base URL configuration and automatic JWT token
 * attachment. Provides a clean interface used by all Pinia stores.
 */

import axios from 'axios'
import { useAuthStore } from '../stores/auth'

// Create axios instance with base URL
const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add JWT token to every request if available
api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

// Handle 401 responses (expired/invalid tokens)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export function useApi() {
  return api
}

export default api
