import { useEffect, useState } from 'react'
import { ADMIN_API, adminFetch, apiError } from './adminApi'
import type { AccountingDetail, AccountingHistory } from './adminApi'

const yen = (value: number) => `${value.toLocaleString('ja-JP')}円`
const dateTime = (value: string) => new Date(value).toLocaleString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })

export default function AdminAccounting() {
  const detailId = Number(window.location.pathname.split('/').at(-1))
  const showingDetail = Number.isInteger(detailId) && window.location.pathname !== '/admin/accounting'
  const [history, setHistory] = useState<AccountingHistory[]>([])
  const [detail, setDetail] = useState<AccountingDetail | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => { (async () => {
    const response = await adminFetch(`${ADMIN_API}/accounting/history${showingDetail ? `/${detailId}` : ''}`)
    if (!response.ok) { setError(await apiError(response, '会計履歴を取得できませんでした')); return }
    if (showingDetail) setDetail(await response.json()); else setHistory(await response.json())
  })() }, [detailId, showingDetail])
  const reopen = async () => {
    if (!detail || !window.confirm('この会計完了を取り消し、利用中に戻しますか？')) return
    const response = await adminFetch(`${ADMIN_API}/accounting/history/${detail.session_id}/reopen`, { method: 'POST' })
    if (!response.ok) { setError(await apiError(response, '会計完了を取り消せませんでした')); return }
    setMessage('会計完了を取り消しました'); setDetail(null)
  }
  if (showingDetail) return <main className="admin-app"><a className="admin-back-link" href="/admin/accounting">← 会計履歴へ戻る</a><header className="admin-header accounting-detail-header"><div><small>{detail?.table_name ?? 'ACCOUNTING'}</small><h1>会計詳細</h1></div>{detail && <button className="danger-button" onClick={reopen}>会計完了を取り消す</button>}</header>{message && <p className="admin-success">{message}</p>}{error && <p className="admin-error">{error}</p>}{detail && <><dl className="accounting-summary"><div><dt>利用開始</dt><dd>{dateTime(detail.started_at)}</dd></div><div><dt>会計完了</dt><dd>{dateTime(detail.completed_at)}</dd></div><div><dt>会計金額</dt><dd>{yen(detail.total_amount)}</dd></div></dl><div className="accounting-orders">{detail.orders.map((order) => <section key={order.order_id}><header><strong>注文 #{order.order_id}</strong><time>{dateTime(order.ordered_at)}</time></header><div className="admin-table-wrap"><table><thead><tr><th>商品名</th><th>数量</th><th>キャンセル</th><th>注文時価格</th><th>金額</th></tr></thead><tbody>{order.items.map((item) => <tr key={`${order.order_id}-${item.product_id}`}><td><strong>{item.product_name}</strong></td><td>{item.quantity}</td><td>{item.canceled_quantity}</td><td>{yen(item.unit_price)}</td><td>{yen(item.amount)}</td></tr>)}</tbody></table></div></section>)}</div></>}</main>
  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>会計履歴</h1></div></header>{error && <p className="admin-error">{error}</p>}{history.length === 0 && !error ? <div className="admin-empty">会計履歴がありません</div> : <div className="admin-table-wrap"><table><thead><tr><th>テーブル名</th><th>利用開始</th><th>会計完了</th><th>会計金額</th><th>操作</th></tr></thead><tbody>{history.map((item) => <tr key={item.session_id}><td><strong>{item.table_name}</strong></td><td>{dateTime(item.started_at)}</td><td>{dateTime(item.completed_at)}</td><td><strong>{yen(item.total_amount)}</strong></td><td><a className="table-link" href={`/admin/accounting/${item.session_id}`}>詳細</a></td></tr>)}</tbody></table></div>}</main>
}
