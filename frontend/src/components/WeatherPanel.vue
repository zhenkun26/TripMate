<script setup lang="ts">
import type { TripPlan } from '../types'
import { formatDate, formatMonthDayTime } from '../utils/format'

const props = defineProps<{
  tripPlan: TripPlan
}>()

function updatedAtText(): string {
  const formatted = formatMonthDayTime(props.tripPlan.weather_updated_at)
  if (!formatted) {
    return ''
  }
  return props.tripPlan.weather_stale
    ? `更新于 ${formatted}（数据延迟）`
    : `天气数据更新于 ${formatted}`
}

function weatherFor(dateValue: string) {
  return props.tripPlan.weather_info.find((item) => item.date === dateValue)
}
</script>

<template>
  <a-card title="🌤️ 天气信息" :bordered="false">
    <a-space direction="vertical" style="width: 100%">
      <a-typography-text type="secondary" data-testid="weather-updated">
        {{ updatedAtText() }}
      </a-typography-text>
      <a-row :gutter="[12, 12]">
        <a-col v-for="day in tripPlan.days" :key="day.date" :xs="24" :sm="12" :md="8">
          <div class="weather-card">
            <div class="weather-date">{{ formatDate(day.date) }}</div>
            <template v-if="weatherFor(day.date)">
              <div class="weather-main">
                {{ weatherFor(day.date)?.day_weather }} {{ weatherFor(day.date)?.day_temp }}°C
              </div>
              <div class="weather-sub">
                夜间 {{ weatherFor(day.date)?.night_weather }}
                {{ weatherFor(day.date)?.night_temp }}°C
              </div>
              <div class="weather-sub">
                {{ weatherFor(day.date)?.wind_direction }}
                {{ weatherFor(day.date)?.wind_power }}
              </div>
            </template>
            <template v-else>
              <div class="weather-missing">该日期暂无预报</div>
            </template>
          </div>
        </a-col>
      </a-row>
      <a-typography-paragraph type="secondary" style="margin-bottom: 0">
        预报通常覆盖未来 3-4 天，仅供参考；天气预报存在不确定性，出行前请以最新预报为准。
      </a-typography-paragraph>
    </a-space>
  </a-card>
</template>

<style scoped>
.weather-card {
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px;
  text-align: center;
  background: #fafafa;
}

.weather-date {
  font-weight: 600;
  margin-bottom: 6px;
}

.weather-main {
  font-size: 18px;
  color: #1e90ff;
  font-weight: 600;
}

.weather-sub {
  color: #888;
  font-size: 13px;
}

.weather-missing {
  color: #aaa;
  padding: 8px 0;
}
</style>
