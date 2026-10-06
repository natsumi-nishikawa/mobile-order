import { useEffect, useState } from 'react'
import { STAFF_API, staffError, staffFetch } from './staffApi'
import type { StaffAccounting as StaffAccountingData } from './staffApi'

const yen = (value: number) => `${value.toLocaleString('ja-JP')}円`

export default function StaffAccounting({ sessionId }: { sessionId: number }) {
  const [accounting, setAccounting] = useState<StaffAccountingData | null>(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const load = async () => {
      const response = await staffFetch(`${STAFF_API}/sessions/${sessionId}/accounting`)
      if (response.ok) setAccounting(await response.json())
      else setError(await staffError(response, '会計情報を取得できませんでした'))
    }
    load()
  }, [sessionId])

  const complete = async () => {
    if (!accounting || !window.confirm(`${accounting.table_name}の会計を完了しますか？`)) return
    setSubmitting(true); setError('')
    const response = await staffFetch(`${STAFF_API}/sessions/${sessionId}/complete`, { method: 'POST' })
    if (!response.ok) { setError(await staffError(response, '会計を完了できませんでした')); setSubmitting(false); return }
    window.location.href = '/staff/tables'
  }

  return <main className="staff-main"><a className="staff-back-link" href="/staff/tables">← テーブル一覧に戻る</a><header className="staff-heading accounting-heading"><div><small>S-06</small><h1>会計確認</h1></div>{accounting && <strong>{accounting.table_name}</strong>}</header>{error && <p className="staff-alert error">{error}</p>}{!accounting && !error ? <p>読み込み中...</p> : accounting && <><div className="staff-accounting-table"><table><thead><tr><th>商品名</th><th>注文時単価</th><th>注文数量</th><th>キャンセル</th><th>会計対象</th><th>小計</th></tr></thead><tbody>{accounting.items.map((item) => <tr className={item.billable_quantity === 0 ? 'fully-canceled' : ''} key={item.order_item_id}><td><strong>{item.product_name}</strong>{item.billable_quantity === 0 && <small>全キャンセル</small>}</td><td>{yen(item.unit_price)}</td><td>{item.quantity}</td><td>{item.canceled_quantity}</td><td>{item.billable_quantity}</td><td>{yen(item.subtotal)}</td></tr>)}</tbody></table>{accounting.items.length === 0 && <div className="staff-empty">注文はありません</div>}</div><section className="staff-accounting-summary"><div><span>会計対象の注文点数</span><strong>{accounting.total_item_count}点</strong></div><div><span>合計金額</span><strong>{yen(accounting.total_amount)}</strong></div></section><div className="staff-accounting-actions"><a href="/staff/tables">テーブル一覧に戻る</a><button className="staff-primary" disabled={submitting} onClick={complete}>{submitting ? '処理中...' : '会計完了'}</button></div></>}</main>
}
