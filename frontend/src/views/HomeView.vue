<script setup lang="ts">
import { reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { generateTripPlan } from '../services/api'
import { PLAN_STORAGE_KEY } from '../services/storage'
import type { TripPlanRequest } from '../types'

const router = useRouter()
const loading = ref(false)
const progress = ref(0)
const statusText = ref('')

const form = reactive<TripPlanRequest>({
  city: '',
  start_date: '',
  end_date: '',
  days: 3,
  preferences: '',
  budget: '舒适型',
  transportation: '公共交通',
  accommodation: '舒适型酒店',
})

const rules = {
  city: [{ required: true, message: '请输入目的地城市', trigger: 'blur' }],
  start_date: [{ required: true, message: '请选择开始日期', trigger: 'change' }],
  end_date: [{ required: true, message: '请选择结束日期', trigger: 'change' }],
  days: [{ required: true, message: '请输入旅行天数', trigger: 'blur' }],
  preferences: [{ required: true, message: '请输入旅行偏好', trigger: 'blur' }],
}

let progressTimer: number | undefined

function startProgress(): void {
  progress.value = 0
  progressTimer = window.setInterval(() => {
    if (progress.value < 90) {
      progress.value += 8
      if (progress.value <= 30) {
        statusText.value = '🔍 正在搜索景点...'
      } else if (progress.value <= 50) {
        statusText.value = '🌤️ 正在查询天气...'
      } else if (progress.value <= 70) {
        statusText.value = '🏨 正在推荐酒店...'
      } else {
        statusText.value = '📋 正在生成行程计划...'
      }
    }
  }, 400)
}

function stopProgress(): void {
  if (progressTimer !== undefined) {
    window.clearInterval(progressTimer)
    progressTimer = undefined
  }
}

async function handleSubmit(): Promise<void> {
  if (!form.city || !form.start_date || !form.end_date || !form.preferences) {
    message.warning('请填写完整必填项')
    return
  }
  if (form.end_date < form.start_date) {
    message.warning('结束日期不能早于开始日期')
    return
  }
  loading.value = true
  startProgress()
  try {
    const tripPlan = await generateTripPlan({
      ...form,
      days: Number(form.days),
    })
    sessionStorage.setItem(PLAN_STORAGE_KEY, JSON.stringify(tripPlan))
    progress.value = 100
    statusText.value = '✅ 行程生成完成！'
    router.push({ name: 'result' })
  } catch (error) {
    const detail = error instanceof Error ? error.message : ''
    message.error(detail || '生成计划失败，请稍后重试')
  } finally {
    stopProgress()
    loading.value = false
  }
}
</script>

<template>
  <div class="home-page">
    <a-card class="home-card">
      <template #title>
        <div class="home-title">✈️ 智能旅行规划</div>
      </template>
      <a-alert
        type="info"
        show-icon
        message="输入目的地与偏好，我们将基于真实 POI 与天气数据生成完整行程；首次生成约需 5-15 秒，请耐心等待。"
        style="margin-bottom: 20px"
      />
      <a-form
        layout="vertical"
        :model="form"
        :rules="rules"
        @finish="handleSubmit"
      >
        <a-row :gutter="16">
          <a-col :xs="24" :md="12">
            <a-form-item label="目的地城市" name="city">
              <a-input v-model:value="form.city" placeholder="如：北京" allow-clear />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item label="旅行偏好" name="preferences">
              <a-input
                v-model:value="form.preferences"
                placeholder="如：历史文化 / 自然风光 / 亲子乐园"
                allow-clear
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="开始日期" name="start_date">
              <a-date-picker
                v-model:value="form.start_date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                placeholder="选择开始日期"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="结束日期" name="end_date">
              <a-date-picker
                v-model:value="form.end_date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                placeholder="选择结束日期"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="旅行天数" name="days">
              <a-input-number
                v-model:value="form.days"
                :min="1"
                :max="14"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="预算档位">
              <a-select v-model:value="form.budget">
                <a-select-option value="经济型">经济型</a-select-option>
                <a-select-option value="舒适型">舒适型</a-select-option>
                <a-select-option value="豪华型">豪华型</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="交通方式">
              <a-select v-model:value="form.transportation">
                <a-select-option value="公共交通">公共交通</a-select-option>
                <a-select-option value="自驾">自驾</a-select-option>
                <a-select-option value="打车">打车</a-select-option>
                <a-select-option value="包车">包车</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="8">
            <a-form-item label="住宿类型">
              <a-select v-model:value="form.accommodation">
                <a-select-option value="经济型酒店">经济型酒店</a-select-option>
                <a-select-option value="舒适型酒店">舒适型酒店</a-select-option>
                <a-select-option value="豪华酒店">豪华酒店</a-select-option>
                <a-select-option value="民宿">民宿</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <div v-if="loading" class="progress-area">
          <a-progress :percent="progress" status="active" />
          <a-typography-text type="secondary">{{ statusText }}</a-typography-text>
        </div>

        <a-button
          type="primary"
          size="large"
          block
          :loading="loading"
          @click="handleSubmit"
        >
          开始规划
        </a-button>
      </a-form>
    </a-card>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 900px;
  margin: 0 auto;
}

.home-card {
  border-radius: 12px;
}

.home-title {
  font-size: 18px;
  font-weight: 600;
}

.progress-area {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
