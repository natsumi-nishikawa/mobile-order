import { storeFetch } from './storeAuth'

export const STAFF_API = 'http://localhost:8000/api/staff'
export const staffFetch = storeFetch

export type ActiveSession = { id: number; status: string; started_at: string }
export type StaffTable = { id: number; table_name: string; is_in_use: boolean; active_session: ActiveSession | null }
export type StaffOrderItem = { id: number; product_id: number; product_name: string; quantity: number; canceled_quantity: number; served_quantity: number; effective_quantity: number; unit_price: number }
export type StaffOrder = { id: number; session_id: number; table_id: number; table_name: string; order_type: string; ordered_at: string; items: StaffOrderItem[] }
export type StaffCategory = { id: number; name: string; display_order: number }
export type StaffProduct = { id: number; name: string; price: number; is_sold_out: boolean; category_ids: number[] }
export type StaffAccountingItem = { order_item_id: number; product_name: string; unit_price: number; quantity: number; canceled_quantity: number; billable_quantity: number; subtotal: number }
export type StaffAccounting = { session_id: number; table_id: number; table_name: string; items: StaffAccountingItem[]; total_item_count: number; total_amount: number }

export async function staffError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({}))
  return data.detail ?? fallback
}
