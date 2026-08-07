<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import html2canvas from 'html2canvas'
import BudgetCard from '../components/BudgetCard.vue'
import DayPlanCard from '../components/DayPlanCard.vue'
import TripMap from '../components/TripMap.vue'
import WeatherPanel from '../components/WeatherPanel.vue'
import { fetchSharedPlan } from '../services/api'
import { PLAN_STORAGE_KEY } from '../services/storage'
import type { TripPlan } from '../types'
import { formatDate } from '../utils/format'

const router = useRouter()
const route = useRoute()
const plan = ref<TripPlan | null>(null)
const sharing = ref(false)
const activeSection = ref('overview')

const menuItems = [
  { key: 'overview', label: '📋 行程概览' },
  { key: 'budget', label: '💰 预算明细' },
  { key: 'map', label: '🗺️ 地图' },
  { key: 'days', label: '📅 每日行程' },
  { key: 'weather', label: '🌤️ 天气' },
]

const summaryText = computed(() => {
  if (!plan.value) {
    return ''
  }
  return `${plan.value.city} · ${formatDate(plan.value.start_date)} 至 ${formatDate(plan.value.end_date)} · ${plan.value.days.length} 天`
})

const shareLink = computed(() => {
  if (!plan.value?.share_token) {
    return ''
  }
  return `${window.location.origin}/result?token=${plan.value.share_token}`
})

onMounted(async () => {
  const raw = sessionStorage.getItem(PLAN_STORAGE_KEY)
  if (raw) {
    try {
      plan.value = JSON.parse(raw) as TripPlan
      return
    } catch {
      message.warning('行程数据已失效，请重新规划')
      router.replace({ name: 'home' })
      return
    }
  }
  // 本地无数据时，尝试按分享链接的 token 从后端加载
  const token = route.query.token
  if (typeof token === 'string' && token) {
    try {
      plan.value = await fetchSharedPlan(token)
      return
    } catch (error) {
      message.warning(error instanceof Error ? error.message : '分享行程不存在或已过期')
      router.replace({ name: 'home' })
      return
    }
  }
  message.warning('暂无行程数据，请先规划')
  router.replace({ name: 'home' })
})

async function copyShareLink(): Promise<void> {
  if (!shareLink.value) {
    return
  }
  try {
    await navigator.clipboard.writeText(shareLink.value)
    message.success('分享链接已复制，发给朋友看看吧')
  } catch {
    message.error('复制失败，请手动复制地址栏链接')
  }
}

function scrollToSection(key: string): void {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

function handleMenuClick(info: { key: string | number }): void {
  scrollToSection(String(info.key))
}

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.arcTo(x + width, y, x + width, y + height, radius)
  ctx.arcTo(x + width, y + height, x, y + height, radius)
  ctx.arcTo(x, y + height, x, y, radius)
  ctx.arcTo(x, y, x + width, y, radius)
  ctx.closePath()
}

async function handleShare(): Promise<void> {
  const target = document.getElementById('share-target')
  if (!target || !plan.value) {
    return
  }
  sharing.value = true
  try {
    const canvas = await html2canvas(target, {
      scale: 2,
      backgroundColor: '#ffffff',
      useCORS: true,
    })
    const ctx = canvas.getContext('2d')
    if (ctx) {
      const width = canvas.width
      const height = canvas.height
      // 品牌水印
      ctx.fillStyle = 'rgba(30, 144, 255, 0.95)'
      ctx.font = 'bold 44px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('TripMate · 智能旅行助手', width / 2, height - 56)
      // “生成我的行程”入口按钮
      const buttonWidth = 380
      const buttonHeight = 76
      const buttonX = width / 2 - buttonWidth / 2
      const buttonY = height - 148
      ctx.fillStyle = '#1e90ff'
      drawRoundedRect(ctx, buttonX, buttonY, buttonWidth, buttonHeight, 38)
      ctx.fill()
      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 34px "PingFang SC", "Microsoft YaHei", sans-serif'
      ctx.fillText('生成我的行程', width / 2, buttonY + buttonHeight / 2 + 12)
    }
    const link = document.createElement('a')
    link.download = `${plan.value.city}旅行计划.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
    message.success('分享图已生成，快去分享吧')
  } catch {
    message.error('生成分享图失败，请稍后重试')
  } finally {
    sharing.value = false
  }
}
</script>

<template>
  <div v-if="plan" class="result-page">
    <a-row :gutter="24">
      <a-col :xs="0" :md="6">
        <a-menu
          mode="inline"
          class="side-menu"
          :selected-keys="[activeSection]"
          @click="handleMenuClick"
        >
          <a-menu-item v-for="item in menuItems" :key="item.key">
            {{ item.label }}
          </a-menu-item>
        </a-menu>
      </a-col>
      <a-col :xs="24" :md="18">
        <div class="share-bar">
          <a-button v-if="shareLink" class="share-link-btn" @click="copyShareLink">
            🔗 复制分享链接
          </a-button>
          <a-button type="primary" :loading="sharing" @click="handleShare">
            📸 生成分享图
          </a-button>
        </div>
        <div id="share-target" class="share-target">
          <section id="overview" class="section">
            <a-card :bordered="false">
              <template #title>
                <span class="section-title">📋 行程概览 · {{ plan.city }}</span>
              </template>
              <a-typography-paragraph class="summary-text">
                {{ summaryText }}
              </a-typography-paragraph>
              <a-alert
                v-for="(notice, index) in plan.notices"
                :key="index"
                type="warning"
                show-icon
                :message="notice"
                style="margin-bottom: 8px"
              />
              <a-typography-paragraph class="suggestions">
                {{ plan.overall_suggestions }}
              </a-typography-paragraph>
            </a-card>
          </section>

          <section v-if="plan.budget" id="budget" class="section">
            <BudgetCard :budget="plan.budget" />
          </section>

          <section id="map" class="section">
            <a-card title="🗺️ 行程地图" :bordered="false">
              <TripMap v-if="plan.map_image_url" :trip-plan="plan" />
            </a-card>
          </section>

          <section id="days" class="section">
            <a-typography-title :level="4">📅 每日行程</a-typography-title>
            <DayPlanCard v-for="day in plan.days" :key="day.date" :day="day" />
          </section>

          <section id="weather" class="section">
            <WeatherPanel :trip-plan="plan" />
          </section>

          <div class="recall-hook">出发前 3 天回来刷新，天气会更准</div>
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.side-menu {
  position: sticky;
  top: 24px;
  border-radius: 8px;
}

.share-bar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 12px;
}

.share-target {
  background: #ffffff;
  border-radius: 12px;
  padding: 20px 20px 12px;
}

.section {
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
}

.summary-text {
  font-size: 15px;
  color: #555;
}

.suggestions {
  white-space: pre-wrap;
  color: #333;
}

.recall-hook {
  text-align: center;
  color: #999;
  padding: 16px 0 12px;
  font-size: 14px;
}
</style>
