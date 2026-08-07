import axios from 'axios'
import type { ApiEnvelope, TripPlan, TripPlanRequest } from '../types'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 分钟超时（LLM 生成 + 数据采集）
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.response.use(
  (response) => {
    const body = response.data as ApiEnvelope<unknown> | undefined
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return response
  },
  (error: unknown) => {
    const axiosError = error as { message?: string }
    return Promise.reject(new Error(axiosError.message || '网络错误'))
  },
)

export async function generateTripPlan(request: TripPlanRequest): Promise<TripPlan> {
  const response = await api.post<ApiEnvelope<TripPlan>>('/trip/plan', request)
  const data = response.data.data
  if (!data) {
    throw new Error('生成计划失败，请稍后重试')
  }
  return data
}

export async function fetchSharedPlan(token: string): Promise<TripPlan> {
  const response = await api.get<ApiEnvelope<TripPlan>>(`/trip/plan/${token}`)
  const data = response.data.data
  if (!data) {
    throw new Error('分享行程不存在或已过期')
  }
  return data
}

export function staticMapUrl(mapImageUrl: string): string {
  return mapImageUrl
}
