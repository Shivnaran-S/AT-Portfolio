<script setup>
const props = defineProps({
  holdings: { type: Array, required: true },
})

function formatCurrency(value) {
  return '₹' + Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
</script>

<template>
  <div v-if="holdings.length === 0" class="text-center text-secondary" style="padding: var(--space-2xl);">
    <p style="font-size: 2rem;">📦</p>
    <p class="mt-md">No holdings yet.</p>
  </div>

  <table v-else class="data-table">
    <thead>
      <tr>
        <th>Stock</th>
        <th>Sector</th>
        <th>Qty</th>
        <th>Avg Price</th>
        <th>Current Price</th>
        <th>Invested</th>
        <th>Current Value</th>
        <th>P&L</th>
        <th>P&L %</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="h in holdings" :key="h.stock_symbol">
        <td class="font-bold">{{ h.stock_name }}</td>
        <td><span class="badge badge-info">{{ h.sector }}</span></td>
        <td class="font-bold">{{ h.quantity }}</td>
        <td class="font-mono">{{ formatCurrency(h.average_buy_price) }}</td>
        <td class="font-mono">{{ formatCurrency(h.current_price) }}</td>
        <td class="font-mono">{{ formatCurrency(h.invested_amount) }}</td>
        <td class="font-mono">{{ formatCurrency(h.current_value) }}</td>
        <td class="font-mono font-bold" :class="h.profit_loss >= 0 ? 'text-profit' : 'text-loss'">
          {{ h.profit_loss >= 0 ? '+' : '' }}{{ formatCurrency(h.profit_loss) }}
        </td>
        <td class="font-mono font-bold" :class="h.profit_loss_percent >= 0 ? 'text-profit' : 'text-loss'">
          {{ h.profit_loss_percent >= 0 ? '+' : '' }}{{ h.profit_loss_percent.toFixed(2) }}%
        </td>
      </tr>
    </tbody>
    <!-- Totals Row -->
    <tfoot>
      <tr style="border-top: 2px solid var(--border-color);">
        <td colspan="5" class="font-bold" style="text-align: right;">Total</td>
        <td class="font-mono font-bold">
          {{ formatCurrency(holdings.reduce((sum, h) => sum + h.invested_amount, 0)) }}
        </td>
        <td class="font-mono font-bold">
          {{ formatCurrency(holdings.reduce((sum, h) => sum + h.current_value, 0)) }}
        </td>
        <td
          class="font-mono font-bold"
          :class="holdings.reduce((sum, h) => sum + h.profit_loss, 0) >= 0 ? 'text-profit' : 'text-loss'"
        >
          {{ formatCurrency(holdings.reduce((sum, h) => sum + h.profit_loss, 0)) }}
        </td>
        <td></td>
      </tr>
    </tfoot>
  </table>
</template>
