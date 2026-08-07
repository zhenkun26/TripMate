<script setup lang="ts">
import type { DayPlan } from '../types'
import { formatDate } from '../utils/format'

defineProps<{
  day: DayPlan
}>()

function amapDetailUrl(poiId: string): string {
  return `https://www.amap.com/place/${poiId}`
}
</script>

<template>
  <a-card :bordered="false" class="day-card">
    <template #title>
      <span class="day-title">
        第{{ day.day_index + 1 }}天 · {{ formatDate(day.date) }}
      </span>
    </template>
    <a-space direction="vertical" style="width: 100%">
      <a-typography-paragraph style="margin-bottom: 4px">
        {{ day.description }}
      </a-typography-paragraph>
      <a-space wrap>
        <a-tag color="blue">交通：{{ day.transportation }}</a-tag>
        <a-tag color="cyan">住宿：{{ day.accommodation }}</a-tag>
      </a-space>

      <div v-if="day.hotel" class="hotel-block">
        <a-typography-text strong>{{ day.hotel.name }}</a-typography-text>
        <a-typography-text type="secondary" class="hotel-meta">
          {{ day.hotel.price_range }} · 评分 {{ day.hotel.rating }}
        </a-typography-text>
        <a :href="amapDetailUrl(day.hotel.poi_id)" target="_blank" rel="noopener">
          在高德中查看
        </a>
      </div>

      <a-list :data-source="day.attractions" :split="false">
        <template #renderItem="{ item, index }">
          <a-list-item class="attraction-item">
            <div class="attraction-body">
              <div class="attraction-name">
                <a-badge
                  :count="index + 1"
                  :number-style="{ backgroundColor: '#1e90ff' }"
                  style="margin-right: 8px"
                />
                <a-typography-text strong>{{ item.name }}</a-typography-text>
                <span v-if="item.rating" class="attraction-rating">
                  ⭐ {{ item.rating.toFixed(1) }}
                </span>
              </div>
              <a-typography-paragraph type="secondary" class="attraction-desc">
                {{ item.description }}
              </a-typography-paragraph>
              <a-space wrap>
                <a-tag>{{ item.visit_duration }} 分钟</a-tag>
                <a-tag color="orange">门票 {{ item.ticket_price }} 元</a-tag>
                <a :href="amapDetailUrl(item.poi_id)" target="_blank" rel="noopener">
                  在高德中查看
                </a>
              </a-space>
            </div>
          </a-list-item>
        </template>
      </a-list>
    </a-space>
  </a-card>
</template>

<style scoped>
.day-card {
  margin-bottom: 16px;
}

.day-title {
  font-size: 16px;
}

.hotel-block {
  background: #f0f7ff;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.hotel-meta {
  flex: 1;
  min-width: 160px;
}

.attraction-item {
  padding: 10px 0;
}

.attraction-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.attraction-rating {
  color: #fa8c16;
  font-size: 13px;
}

.attraction-desc {
  margin: 6px 0 4px;
}
</style>
