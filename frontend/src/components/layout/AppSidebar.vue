<script setup>
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const navItems = [
  { name: 'Dashboard', path: '/', icon: '📊' },
  { name: 'Portfolio', path: '/portfolio', icon: '💼' },
  { name: 'Trading', path: '/trading', icon: '📈' },
  { name: 'Demo', path: '/demo', icon: '🎮' },
]

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <aside class="sidebar">
    <!-- Brand -->
    <div class="sidebar-brand">
      <div class="brand-logo">AT</div>
      <div>
        <div class="brand-name">AT-PORTFOLIO</div>
        <div class="brand-sub">AI-Powered Trading</div>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="sidebar-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item"
        :class="{ active: route.path === item.path }"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span>{{ item.name }}</span>
      </router-link>
    </nav>

    <!-- User Section -->
    <div class="sidebar-footer">
      <div v-if="authStore.user" class="user-info">
        <div class="user-avatar">{{ authStore.user.username[0].toUpperCase() }}</div>
        <div>
          <div class="user-name">{{ authStore.user.username }}</div>
          <div class="user-role">Investor</div>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm w-full mt-md" @click="handleLogout">
        Logout
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-2xl);
  padding-bottom: var(--space-lg);
  border-bottom: 1px solid var(--border-color);
}

.brand-logo {
  width: 40px;
  height: 40px;
  background: var(--gradient-primary);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  font-size: var(--font-size-sm);
  color: white;
}

.brand-name {
  font-weight: 800;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
}

.brand-sub {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: 10px 14px;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  transition: all var(--transition-fast);
  text-decoration: none;
}

.nav-item:hover {
  background: var(--bg-glass-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: rgba(16, 185, 129, 0.1);
  color: var(--accent-primary);
  font-weight: 600;
}

.nav-icon {
  font-size: 1.1rem;
}

.sidebar-footer {
  padding-top: var(--space-lg);
  border-top: 1px solid var(--border-color);
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.user-avatar {
  width: 36px;
  height: 36px;
  background: var(--gradient-accent);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: var(--font-size-sm);
  color: white;
}

.user-name {
  font-weight: 600;
  font-size: var(--font-size-sm);
}

.user-role {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
}
</style>
