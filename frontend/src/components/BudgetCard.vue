<script setup lang="ts">
import type { Budget } from '../types'

defineProps<{
  budget: Budget
}>()
</script>

<template>
  <a-card title="💰 预算明细" :bordered="false">
    <a-row :gutter="16">
      <a-col :xs="24" :sm="8">
        <a-statistic title="景点门票" :value="budget.total_attractions" suffix="元" />
      </a-col>
      <a-col :xs="24" :sm="8">
        <a-statistic title="酒店住宿" :value="budget.total_hotels" suffix="元" />
      </a-col>
      <a-col :xs="24" :sm="8">
        <a-statistic title="交通费用" :value="budget.total_transportation" suffix="元" />
      </a-col>
    </a-row>
    <a-divider />
    <a-row>
      <a-col :span="24" style="text-align: center">
        <a-statistic
          title="预估总费用"
          :value="budget.total"
          suffix="元"
          :value-style="{ color: '#cf1322', fontSize: '28px', fontWeight: 'bold' }"
        />
      </a-col>
    </a-row>
  </a-card>
</template>
