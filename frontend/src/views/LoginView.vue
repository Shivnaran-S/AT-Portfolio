<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')

async function handleLogin() {
  const success = await authStore.login(username.value, password.value)
  if (success) {
    router.push('/')
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand">
        <div class="brand-name">AT-PORTFOLIO</div>
      </div>
      <h1>Welcome Back</h1>
      <p class="subtitle">Sign in to manage your investments</p>

      <div v-if="authStore.error" class="error-message">
        {{ authStore.error }}
      </div>

      <form @submit.prevent="handleLogin">
        <div class="input-group">
          <label for="login-username">Username</label>
          <input
            id="login-username"
            v-model="username"
            type="text"
            class="input"
            placeholder="Enter your username"
            required
          />
        </div>

        <div class="input-group">
          <label for="login-password">Password</label>
          <input
            id="login-password"
            v-model="password"
            type="password"
            class="input"
            placeholder="Enter your password"
            required
          />
        </div>

        <button
          type="submit"
          class="btn btn-primary btn-lg w-full"
          :disabled="authStore.loading"
        >
          <span v-if="authStore.loading" class="spinner" style="width:18px;height:18px;border-width:2px;"></span>
          <span v-else>Sign In</span>
        </button>
      </form>

      <p class="auth-link">
        Don't have an account?
        <router-link to="/signup">Create one</router-link>
      </p>

      <div class="text-center mt-lg">
        <router-link to="/demo" class="btn btn-gold">
          🎮 Try Demo Mode
        </router-link>
      </div>
    </div>
  </div>
</template>
