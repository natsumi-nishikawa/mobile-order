export const ADMIN_API = 'http://localhost:8000/api/admin'

export type Category = { id: number; name: string; display_order: number }
export type DiningTable = { id: number; table_name: string }
export type BusinessHour = {
  id?: number
  day_of_week: number
  is_open: boolean
  opening_time: string | null
  closing_time: string | null
}
export type AccountingHistory = {
  session_id: number
  table_id: number
  table_name: string
  started_at: string
  completed_at: string
  total_amount: number
}
export type AccountingOrderItem = {
  product_id: number
  product_name: string
  quantity: number
  canceled_quantity: number
  unit_price: number
  amount: number
}
export type AccountingOrder = { order_id: number; ordered_at: string; items: AccountingOrderItem[] }
export type AccountingDetail = AccountingHistory & { orders: AccountingOrder[] }

export async function apiError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({}))
  return data.detail ?? fallback
}
