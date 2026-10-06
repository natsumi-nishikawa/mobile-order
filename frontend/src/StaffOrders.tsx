import { useCallback, useEffect, useState } from 'react'
import { STAFF_API, staffError, staffFetch } from './staffApi'
import type { StaffOrder } from './staffApi'

export default function StaffOrders() {
  const [orders, setOrders] = useState<StaffOrder[]>([])
  const [error, setError] = useState('')
  const load = useCallback(async () => { const response = await staffFetch(`${STAFF_API}/orders`); if (response.ok) setOrders(await response.json()); else setError(await staffError(response, '注文を取得できませんでした')) }, [])
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load(); const timer = window.setInterval(load, 15000); return () => window.clearInterval(timer) }, [load])
  const update = async (itemId: number, kind: 'served' | 'canceled', quantity: number) => { const response = await staffFetch(`${STAFF_API}/order-items/${itemId}/${kind}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ quantity }) }); if (!response.ok) { setError(await staffError(response, '数量を更新できませんでした')); return } setError(''); await load() }
  return <main className="staff-main"><header className="staff-heading"><div><small>STAFF</small><h1>注文一覧</h1></div><button onClick={load}>更新</button></header><p className="staff-note">利用中テーブルの注文を表示しています（15秒ごとに自動更新）</p>{error && <p className="staff-alert error">{error}</p>}{orders.length === 0 ? <div className="staff-empty">現在の注文はありません</div> : <div className="staff-orders">{orders.map((order) => <article key={order.id}><header><div><strong>{order.table_name}</strong><span>注文 #{order.id}{order.order_type === 'staff' ? '・代理注文' : ''}</span></div><time>{new Date(order.ordered_at).toLocaleString('ja-JP')}</time></header>{order.items.map((item) => <div className={`staff-order-item ${item.effective_quantity === 0 ? 'canceled' : item.served_quantity === item.effective_quantity ? 'served' : ''}`} key={item.id}><div className="item-name"><strong>{item.product_name}</strong><span>注文 {item.quantity} / 有効 {item.effective_quantity}</span></div><label>提供済み<input type="number" min="0" max={item.effective_quantity} value={item.served_quantity} onChange={(event) => update(item.id, 'served', Number(event.target.value))} /></label><label>キャンセル<input type="number" min="0" max={item.quantity} value={item.canceled_quantity} onChange={(event) => update(item.id, 'canceled', Number(event.target.value))} /></label><span className="item-state">{item.effective_quantity === 0 ? 'キャンセル' : item.served_quantity === item.effective_quantity ? '提供済み' : '準備中'}</span></div>)}</article>)}</div>}</main>
}
