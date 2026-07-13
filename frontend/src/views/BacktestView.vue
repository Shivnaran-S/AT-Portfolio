<script setup>
import { ref, computed } from 'vue'
import api from '../composables/useApi'

// State
const activeTab = ref('portfolio') // 'portfolio' | 'trading'
const loading = ref(false)
const error = ref(null)

// Portfolio backtest
const portfolioResult = ref(null)
const portfolioPeriod = ref('2y')
const portfolioFreq = ref('monthly')

// Trading backtest
const tradingResult = ref(null)
const tradingShares = ref(50)
const tradingOrderType = ref('BUY')

async function runPortfolioBacktest() {
  loading.value = true
  error.value = null
  portfolioResult.value = null
  try {
    const response = await api.post('/backtest/portfolio', {
      period: portfolioPeriod.value,
      rebalance_frequency: portfolioFreq.value,
      lookback_months: 6,
    })
    portfolioResult.value = response.data
  } catch (err) {
    error.value = err.response?.data?.detail || 'Portfolio backtest failed.'
  } finally {
    loading.value = false
  }
}

async function runTradingBacktest() {
  loading.value = true
  error.value = null
  tradingResult.value = null
  try {
    const response = await api.post('/backtest/trading', {
      total_shares: tradingShares.value,
      order_type: tradingOrderType.value,
    })
    tradingResult.value = response.data
  } catch (err) {
    error.value = err.response?.data?.detail || 'Trading backtest failed.'
  } finally {
    loading.value = false
  }
}

function formatPercent(val) {
  if (val === null || val === undefined) return '—'
  const pct = (val * 100).toFixed(2)
  const sign = val > 0 ? '+' : ''
  return sign + pct + '%'
}

function formatRatio(val) {
  if (val === null || val === undefined) return '—'
  return val.toFixed(4)
}

// Expanded stock details in trading results
const expandedStocks = ref(new Set())
function toggleStock(symbol) {
  if (expandedStocks.value.has(symbol)) {
    expandedStocks.value.delete(symbol)
  } else {
    expandedStocks.value.add(symbol)
  }
}

const ppoMetrics = computed(() => portfolioResult.value?.ppo_agent)
const benchMetrics = computed(() => portfolioResult.value?.benchmark)
</script>

<template>
  <div class="backtest-page">
    <!-- Header -->
    <div class="backtest-header">
      <div class="header-content">
        <span style="font-size:2.5rem;">📋</span>
        <div>
          <h1>Backtesting</h1>
          <p class="text-secondary">Evaluate PPO agent performance on historical data</p>
        </div>
      </div>
    </div>

    <!-- Tab Switcher -->
    <div class="tab-bar">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'portfolio' }"
        @click="activeTab = 'portfolio'"
      >
        📊 Portfolio Agent
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'trading' }"
        @click="activeTab = 'trading'"
      >
        ⚡ Trading Agent
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-message mb-lg">{{ error }}</div>

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- Portfolio Backtest Tab                                         -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <div v-if="activeTab === 'portfolio'" class="tab-content">
      <div class="config-card">
        <h3>Configuration</h3>
        <div class="config-grid">
          <div class="input-group">
            <label for="bt-period">Historical Period</label>
            <select id="bt-period" v-model="portfolioPeriod" class="input">
              <option value="1y">1 Year</option>
              <option value="2y">2 Years</option>
              <option value="3y">3 Years</option>
              <option value="5y">5 Years</option>
            </select>
          </div>
          <div class="input-group">
            <label for="bt-freq">Rebalance Frequency</label>
            <select id="bt-freq" v-model="portfolioFreq" class="input">
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
            </select>
          </div>
        </div>
        <button
          class="btn btn-primary btn-lg w-full mt-lg"
          :disabled="loading"
          @click="runPortfolioBacktest"
        >
          <template v-if="loading">
            <span class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px;"></span>
            Running Backtest...
          </template>
          <template v-else>🚀 Run Portfolio Backtest</template>
        </button>
      </div>

      <!-- Results -->
      <div v-if="portfolioResult && ppoMetrics" class="results-section">
        <h2 class="section-title">Performance Metrics</h2>

        <!-- Metrics comparison table -->
        <div class="card">
          <table class="metrics-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>PPO Agent</th>
                <th>Equal-Weight Benchmark</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Annualized Return</td>
                <td :class="ppoMetrics.annualized_return >= 0 ? 'text-profit' : 'text-loss'">
                  {{ formatPercent(ppoMetrics.annualized_return) }}
                </td>
                <td :class="benchMetrics.annualized_return >= 0 ? 'text-profit' : 'text-loss'">
                  {{ formatPercent(benchMetrics.annualized_return) }}
                </td>
              </tr>
              <tr>
                <td>Total Return</td>
                <td :class="ppoMetrics.total_return >= 0 ? 'text-profit' : 'text-loss'">
                  {{ formatPercent(ppoMetrics.total_return) }}
                </td>
                <td :class="benchMetrics.total_return >= 0 ? 'text-profit' : 'text-loss'">
                  {{ formatPercent(benchMetrics.total_return) }}
                </td>
              </tr>
              <tr>
                <td>Sharpe Ratio</td>
                <td class="font-mono font-bold">{{ formatRatio(ppoMetrics.sharpe_ratio) }}</td>
                <td class="font-mono">{{ formatRatio(benchMetrics.sharpe_ratio) }}</td>
              </tr>
              <tr>
                <td>Sortino Ratio</td>
                <td class="font-mono font-bold">{{ formatRatio(ppoMetrics.sortino_ratio) }}</td>
                <td class="font-mono">{{ formatRatio(benchMetrics.sortino_ratio) }}</td>
              </tr>
              <tr>
                <td>Max Drawdown</td>
                <td class="text-loss">{{ formatPercent(ppoMetrics.max_drawdown) }}</td>
                <td class="text-loss">{{ formatPercent(benchMetrics.max_drawdown) }}</td>
              </tr>
              <tr>
                <td>Annualized Volatility</td>
                <td class="font-mono">{{ formatPercent(ppoMetrics.annualized_volatility) }}</td>
                <td class="font-mono">{{ formatPercent(benchMetrics.annualized_volatility) }}</td>
              </tr>
              <tr>
                <td>Calmar Ratio</td>
                <td class="font-mono font-bold">{{ formatRatio(ppoMetrics.calmar_ratio) }}</td>
                <td class="font-mono">{{ formatRatio(benchMetrics.calmar_ratio) }}</td>
              </tr>
              <tr>
                <td>Win Rate</td>
                <td class="font-mono">{{ formatPercent(ppoMetrics.win_rate) }}</td>
                <td class="font-mono">{{ formatPercent(benchMetrics.win_rate) }}</td>
              </tr>
              <tr v-if="ppoMetrics.excess_return_vs_benchmark !== undefined">
                <td class="font-bold">Excess Return vs Benchmark</td>
                <td :class="ppoMetrics.excess_return_vs_benchmark >= 0 ? 'text-profit' : 'text-loss'" class="font-bold">
                  {{ formatPercent(ppoMetrics.excess_return_vs_benchmark) }}
                </td>
                <td>—</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Equity Curve (text representation) -->
        <div v-if="portfolioResult.equity_curve" class="card mt-lg">
          <h3 class="mb-md">Equity Curve Summary</h3>
          <div class="equity-summary">
            <div class="equity-stat">
              <span class="label">PPO Final Value</span>
              <span class="value font-mono" :class="portfolioResult.equity_curve.ppo?.slice(-1)?.[0] >= 1 ? 'text-profit' : 'text-loss'">
                {{ portfolioResult.equity_curve.ppo?.slice(-1)?.[0]?.toFixed(4) || '—' }}x
              </span>
            </div>
            <div class="equity-stat">
              <span class="label">Benchmark Final Value</span>
              <span class="value font-mono" :class="portfolioResult.equity_curve.benchmark?.slice(-1)?.[0] >= 1 ? 'text-profit' : 'text-loss'">
                {{ portfolioResult.equity_curve.benchmark?.slice(-1)?.[0]?.toFixed(4) || '—' }}x
              </span>
            </div>
            <div class="equity-stat">
              <span class="label">Data Points</span>
              <span class="value font-mono">{{ portfolioResult.equity_curve.ppo?.length || 0 }}</span>
            </div>
            <div class="equity-stat">
              <span class="label">Rebalance Periods</span>
              <span class="value font-mono">{{ portfolioResult.backtest_config?.num_rebalance_periods || 0 }}</span>
            </div>
          </div>
        </div>

        <!-- Weight History -->
        <div v-if="portfolioResult.weight_history?.length" class="card mt-lg">
          <h3 class="mb-md">Weight History (last 3 rebalances)</h3>
          <div v-for="wh in portfolioResult.weight_history.slice(-3)" :key="wh.date" class="weight-entry mb-md">
            <strong>{{ wh.date }}</strong>
            <div class="weight-pills">
              <span
                v-for="(w, sym) in wh.weights"
                :key="sym"
                class="weight-pill"
              >
                {{ sym.replace('.NS', '') }}: {{ (w * 100).toFixed(1) }}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════ -->
    <!-- Trading Backtest Tab                                           -->
    <!-- ═══════════════════════════════════════════════════════════════ -->
    <div v-if="activeTab === 'trading'" class="tab-content">
      <div class="config-card">
        <h3>Configuration</h3>
        <div class="config-grid">
          <div class="input-group">
            <label for="bt-shares">Shares per Stock</label>
            <input
              id="bt-shares"
              v-model.number="tradingShares"
              type="number"
              class="input"
              min="10"
              max="500"
            />
          </div>
          <div class="input-group">
            <label for="bt-order-type">Order Type</label>
            <select id="bt-order-type" v-model="tradingOrderType" class="input">
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </div>
        </div>
        <button
          class="btn btn-primary btn-lg w-full mt-lg"
          :disabled="loading"
          @click="runTradingBacktest"
        >
          <template v-if="loading">
            <span class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px;"></span>
            Running Backtest...
          </template>
          <template v-else>🚀 Run Trading Backtest</template>
        </button>
      </div>

      <!-- Results -->
      <div v-if="tradingResult?.aggregate_metrics" class="results-section">
        <h2 class="section-title">Aggregate Metrics</h2>

        <div class="card">
          <table class="metrics-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Avg Implementation Shortfall</td>
                <td class="font-mono" :class="tradingResult.aggregate_metrics.avg_implementation_shortfall_pct > 0 ? 'text-loss' : 'text-profit'">
                  {{ tradingResult.aggregate_metrics.avg_implementation_shortfall_pct.toFixed(4) }}%
                </td>
              </tr>
              <tr>
                <td>Avg VWAP Improvement</td>
                <td class="font-mono" :class="tradingResult.aggregate_metrics.avg_vwap_improvement_pct >= 0 ? 'text-profit' : 'text-loss'">
                  {{ tradingResult.aggregate_metrics.avg_vwap_improvement_pct >= 0 ? '+' : '' }}{{ tradingResult.aggregate_metrics.avg_vwap_improvement_pct.toFixed(4) }}%
                </td>
              </tr>
              <tr>
                <td>Avg Slices per Order</td>
                <td class="font-mono font-bold">{{ tradingResult.aggregate_metrics.avg_slices_per_order }}</td>
              </tr>
              <tr>
                <td>Avg Max Single-Slice %</td>
                <td class="font-mono">{{ tradingResult.aggregate_metrics.avg_max_single_slice_pct }}%</td>
              </tr>
              <tr>
                <td>Cost Saving vs Naive</td>
                <td class="font-mono" :class="tradingResult.aggregate_metrics.avg_cost_saving_vs_naive_pct >= 0 ? 'text-profit' : 'text-loss'">
                  {{ tradingResult.aggregate_metrics.avg_cost_saving_vs_naive_pct >= 0 ? '+' : '' }}{{ tradingResult.aggregate_metrics.avg_cost_saving_vs_naive_pct.toFixed(4) }}%
                </td>
              </tr>
              <tr>
                <td>Overall Completion Rate</td>
                <td class="font-mono font-bold">{{ (tradingResult.aggregate_metrics.overall_completion_rate * 100).toFixed(0) }}%</td>
              </tr>
              <tr>
                <td>Stocks Tested</td>
                <td class="font-mono">{{ tradingResult.aggregate_metrics.total_stocks_tested }}</td>
              </tr>
              <tr>
                <td>Days Tested</td>
                <td class="font-mono">{{ tradingResult.aggregate_metrics.total_days_tested }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Per-Stock Results -->
        <h2 class="section-title mt-xl">Per-Stock Results</h2>
        <div v-for="stock in tradingResult.per_stock_results" :key="stock.symbol" class="card mb-md stock-card"
          @click="toggleStock(stock.symbol)"
          style="cursor:pointer;"
        >
          <div class="flex justify-between items-center">
            <div>
              <strong>{{ stock.stock_name }}</strong>
              <span class="text-muted ml-sm">{{ stock.symbol }}</span>
            </div>
            <div class="flex items-center gap-lg">
              <span class="font-mono">{{ stock.avg_slices_per_order }} slices</span>
              <span class="font-mono" :class="stock.avg_vwap_improvement_pct >= 0 ? 'text-profit' : 'text-loss'">
                VWAP: {{ stock.avg_vwap_improvement_pct >= 0 ? '+' : '' }}{{ stock.avg_vwap_improvement_pct.toFixed(4) }}%
              </span>
              <span class="font-mono">{{ stock.num_days_tested }} days</span>
              <span class="expand-arrow" :class="{ expanded: expandedStocks.has(stock.symbol) }">▸</span>
            </div>
          </div>

          <!-- Expanded daily details -->
          <div v-if="expandedStocks.has(stock.symbol)" class="slice-details mt-md" @click.stop>
            <table class="slice-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Slices</th>
                  <th>Max Slice %</th>
                  <th>Shortfall</th>
                  <th>VWAP Imp.</th>
                  <th>vs Naive</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(day, idx) in stock.daily_results" :key="idx">
                  <td>{{ day.date }}</td>
                  <td class="font-mono">{{ day.num_slices }}</td>
                  <td class="font-mono">{{ day.max_single_slice_pct }}%</td>
                  <td class="font-mono" :class="day.implementation_shortfall_pct > 0 ? 'text-loss' : 'text-profit'">
                    {{ day.implementation_shortfall_pct.toFixed(4) }}%
                  </td>
                  <td class="font-mono" :class="day.vwap_improvement_pct >= 0 ? 'text-profit' : 'text-loss'">
                    {{ day.vwap_improvement_pct >= 0 ? '+' : '' }}{{ day.vwap_improvement_pct.toFixed(4) }}%
                  </td>
                  <td class="font-mono" :class="day.cost_saving_vs_naive_pct >= 0 ? 'text-profit' : 'text-loss'">
                    {{ day.cost_saving_vs_naive_pct >= 0 ? '+' : '' }}{{ day.cost_saving_vs_naive_pct.toFixed(4) }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backtest-page {
  min-height: 100vh;
  background: var(--bg-primary);
  padding: var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.backtest-header {
  margin-bottom: var(--space-xl);
}

.header-content {
  display: flex;
  align-items: center;
  gap: var(--space-lg);
}

.header-content h1 {
  font-size: var(--font-size-2xl);
  margin: 0;
}

/* ── Tabs ───────────────────────────────────────────────────────── */

.tab-bar {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-xl);
  padding: var(--space-xs);
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
}

.tab-btn {
  flex: 1;
  padding: var(--space-md) var(--space-lg);
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-glass-hover, rgba(255,255,255,0.05));
}

.tab-btn.active {
  background: var(--bg-card);
  color: var(--accent-primary);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

/* ── Config ─────────────────────────────────────────────────────── */

.config-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xl);
  padding: var(--space-xl);
  margin-bottom: var(--space-xl);
}

.config-card h3 {
  font-size: var(--font-size-lg);
  margin-bottom: var(--space-md);
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-md);
}

/* ── Results ────────────────────────────────────────────────────── */

.results-section {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.section-title {
  font-size: var(--font-size-xl);
  margin-bottom: var(--space-lg);
}

.metrics-table {
  width: 100%;
  border-collapse: collapse;
}

.metrics-table th {
  text-align: left;
  padding: var(--space-sm) var(--space-md);
  color: var(--text-muted);
  font-weight: 500;
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 2px solid var(--border-color);
}

.metrics-table td {
  padding: var(--space-sm) var(--space-md);
  border-bottom: 1px solid rgba(255,255,255,0.03);
  font-size: var(--font-size-sm);
}

.metrics-table tr:hover {
  background: var(--bg-glass-hover, rgba(255,255,255,0.02));
}

/* ── Equity Summary ─────────────────────────────────────────────── */

.equity-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--space-md);
}

.equity-stat {
  display: flex;
  flex-direction: column;
  padding: var(--space-md);
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.equity-stat .label {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-xs);
}

.equity-stat .value {
  font-size: var(--font-size-xl);
  font-weight: 700;
}

/* ── Weight History ─────────────────────────────────────────────── */

.weight-entry {
  padding: var(--space-sm);
  background: var(--bg-glass);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
}

.weight-pills {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
  margin-top: var(--space-xs);
}

.weight-pill {
  padding: 2px 8px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  font-family: var(--font-mono, monospace);
}

/* ── Stock Cards ────────────────────────────────────────────────── */

.stock-card {
  transition: background 0.2s ease;
}

.stock-card:hover {
  background: var(--bg-glass-hover, rgba(255,255,255,0.03));
}

/* ── Shared ──────────────────────────────────────────────────────── */

.expand-arrow {
  transition: transform 0.2s ease;
  font-size: var(--font-size-sm);
  color: var(--text-muted);
}

.expand-arrow.expanded {
  transform: rotate(90deg);
}

.slice-details {
  border-top: 1px solid var(--border-color);
  padding-top: var(--space-sm);
}

.slice-table {
  width: 100%;
  font-size: var(--font-size-sm);
  border-collapse: collapse;
}

.slice-table th {
  text-align: left;
  padding: var(--space-xs) var(--space-sm);
  color: var(--text-muted);
  font-weight: 500;
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--border-color);
}

.slice-table td {
  padding: var(--space-xs) var(--space-sm);
  border-bottom: 1px solid rgba(255,255,255,0.03);
}

.ml-sm { margin-left: var(--space-sm); }
.mt-xl { margin-top: var(--space-xl); }
</style>
