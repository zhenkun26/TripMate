/**
 * 与后端 Pydantic 模型一一对应的 TypeScript 契约。
 * 修改任一侧都必须同步另一侧；禁止 any/object/unknown。
 */

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category: string | null
  rating: number | null
  image_url: string | null
  ticket_price: number
  poi_id: string
}

export interface Hotel {
  name: string
  address: string
  location: Location | null
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost: number
  poi_id: string
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_transportation: number
  total: number
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel: Hotel | null
  attractions: Attraction[]
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  overall_suggestions: string
  budget: Budget | null
  weather_info: WeatherInfo[]
  weather_updated_at: string | null
  weather_stale: boolean
  map_image_url: string | null
  notices: string[]
}

export interface TripPlanRequest {
  city: string
  start_date: string
  end_date: string
  days: number
  preferences: string
  budget: string
  transportation: string
  accommodation: string
}

export interface ApiEnvelope<T> {
  code: number
  data: T | null
  message: string
}

/**
 * 按天配色的图例色板，需与后端 app/services/static_map_service.py DAY_COLORS 保持同步。
 */
export const DAY_COLORS: string[] = [
  '#1E90FF',
  '#FF8C00',
  '#32CD32',
  '#DA70D6',
  '#20B2AA',
  '#FF69B4',
  '#8A2BE2',
  '#CD853F',
  '#5F9EA0',
  '#DC143C',
]
