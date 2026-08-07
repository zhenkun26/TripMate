<script setup lang="ts">
import { ref, watch } from 'vue'
import type { TripPlan } from '../types'
import { DAY_COLORS } from '../types'

const props = defineProps<{
  tripPlan: TripPlan
}>()

const loadFailed = ref(false)

watch(
  () => props.tripPlan.map_image_url,
  () => {
    loadFailed.value = false
  },
)

function onImageError(): void {
  loadFailed.value = true
}
</script>

<template>
  <div v-if="tripPlan.map_image_url && !loadFailed" class="trip-map">
    <img
      :src="tripPlan.map_image_url"
      alt="行程静态地图"
      class="map-image"
      @error="onImageError"
    />
    <div class="legend">
      <span
        v-for="(day, index) in tripPlan.days"
        :key="day.date"
        class="legend-item"
      >
        <span
          class="legend-dot"
          :style="{ backgroundColor: DAY_COLORS[index % DAY_COLORS.length] }"
        />
        第{{ index + 1 }}天
      </span>
      <span class="legend-item">
        <span class="legend-dot legend-line" />
        跨天路线
      </span>
    </div>
  </div>
</template>

<style scoped>
.trip-map {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.map-image {
  width: 100%;
  border-radius: 8px;
  border: 1px solid #eee;
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  justify-content: center;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #666;
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.legend-line {
  width: 24px;
  height: 3px;
  border-radius: 0;
  background: #b0bec5;
}
</style>
