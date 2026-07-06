<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const validationError = ref('')

async function handleSignup() {
  validationError.value = ''

  if (password.value !== confirmPassword.value) {
    validationError.value = 'Passwords do not match.'
    return
  }

  if (password.value.length < 6) {
    validationError.value = 'Password must be at least 6 characters.'
    return
  }

  const success = await authStore.signup(username.value, password.value)
  if (success) {
    // Auto-login after signup
    const loggedIn = await authStore.login(username.value, password.value)
    if (loggedIn) {
      router.push('/')
    }
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand">
        <div class="brand-name">AT-PORTFOLIO</div>
      </div>
      <h1>Create Account</h1>
      <p class="subtitle">Start your investment journey with AI</p>

      <div v-if="authStore.error || validationError" class="error-message">
        {{ validationError || authStore.error }}
      </div>

      <form @submit.prevent="handleSignup">
        <div class="input-group">
          <label for="signup-username">Username</label>
          <input
            id="signup-username"
            v-model="username"
            type="text"
            class="input"
            placeholder="Choose a username"
            minlength="3"
            maxlength="50"
            required
          />
        </div>

        <div class="input-group">
          <label for="signup-password">Password</label>
          <input
            id="signup-password"
            v-model="password"
            type="password"
            class="input"
            placeholder="Create a password (min 6 characters)"
            required
          />
        </div>

        <div class="input-group">
          <label for="signup-confirm">Confirm Password</label>
          <input
            id="signup-confirm"
            v-model="confirmPassword"
            type="password"
            class="input"
            placeholder="Confirm your password"
            required
          />
        </div>

        <button
          type="submit"
          class="btn btn-primary btn-lg w-full"
          :disabled="authStore.loading"
        >
          <span v-if="authStore.loading" class="spinner" style="width:18px;height:18px;border-width:2px;"></span>
          <span v-else>Create Account</span>
        </button>
      </form>

      <p class="auth-link">
        Already have an account?
        <router-link to="/login">Sign in</router-link>
      </p>
    </div>
  </div>
</template>
