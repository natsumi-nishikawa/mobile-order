import { useEffect, useState } from 'react'
import { STAFF_API, staffError, staffFetch } from './staffApi'
import type { StaffCategory, StaffProduct, StaffTable } from './staffApi'

export default function StaffTables() {
  const [tables, setTables] = useState<StaffTable[]>([])
  const [products, setProducts] = useState<StaffProduct[]>([])
  const [categories, setCategories] = useState<StaffCategory[]>([])
  const [activeCategoryId, setActiveCategoryId] = useState<number | 'all'>('all')
  const [ordering, setOrdering] = useState<StaffTable | null>(null)
  const [quantities, setQuantities] = useState<Record<number, number>>({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const load = async () => { const response = await staffFetch(`${STAFF_API}/tables`); if (response.ok) setTables(await response.json()); else setError(await staffError(response, 'テーブルを取得できませんでした')) }
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [])
  const act = async (url: string, success: string) => { setError(''); const response = await staffFetch(`${STAFF_API}${url}`, { method: 'POST' }); if (!response.ok) { setError(await staffError(response, '操作できませんでした')); return } setMessage(success); await load() }
  const openOrder = async (table: StaffTable) => {
    const [categoryResponse, productResponse] = await Promise.all([staffFetch(`${STAFF_API}/categories`), staffFetch(`${STAFF_API}/products`)])
    if (!categoryResponse.ok || !productResponse.ok) { setError(await staffError(!categoryResponse.ok ? categoryResponse : productResponse, '商品を取得できませんでした')); return }
    setCategories(await categoryResponse.json()); setProducts(await productResponse.json()); setQuantities({}); setActiveCategoryId('all'); setOrdering(table)
  }
  const submitOrder = async () => {
    if (!ordering?.active_session) return
    const items = Object.entries(quantities).filter(([, quantity]) => quantity > 0).map(([product_id, quantity]) => ({ product_id: Number(product_id), quantity }))
    if (!items.length) { setError('商品を1つ以上選択してください'); return }
    const response = await staffFetch(`${STAFF_API}/orders`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: ordering.active_session.id, items }) })
    if (!response.ok) { setError(await staffError(response, '注文できませんでした')); return }
    setOrdering(null); setMessage('代理注文を登録しました')
  }
  const menuCategories = products.some((product) => product.category_ids.length === 0)
    ? [...categories, { id: 0, name: 'その他', display_order: Number.MAX_SAFE_INTEGER }]
    : categories
  const visibleProducts = activeCategoryId === 'all'
    ? products
    : products.filter((product) => activeCategoryId === 0 ? product.category_ids.length === 0 : product.category_ids.includes(activeCategoryId))
  const activeCategoryName = activeCategoryId === 'all' ? 'すべての商品' : menuCategories.find((category) => category.id === activeCategoryId)?.name ?? '商品'
  const selectedCount = Object.values(quantities).reduce((sum, quantity) => sum + quantity, 0)
  if (ordering) return <main className="staff-main"><button className="staff-back" onClick={() => setOrdering(null)}>← テーブル一覧へ</button><header className="staff-ordering-heading"><div><small>代理注文</small><h1>{ordering.table_name}</h1></div><strong>選択中 {selectedCount}点</strong></header>{error && <p className="staff-alert error">{error}</p>}<div className="staff-category-tabs"><button className={activeCategoryId === 'all' ? 'active' : ''} onClick={() => setActiveCategoryId('all')}>すべて</button>{menuCategories.map((category) => <button key={category.id} className={activeCategoryId === category.id ? 'active' : ''} onClick={() => setActiveCategoryId(category.id)}>{category.name}</button>)}</div><h2 className="staff-category-title">{activeCategoryName}</h2><div className="staff-products">{visibleProducts.map((product) => <div className={product.is_sold_out ? 'sold-out' : ''} key={product.id}><span><strong>{product.name}</strong><small>{product.price.toLocaleString()}円{product.is_sold_out ? '・売り切れ' : ''}</small></span><input aria-label={`${product.name}の数量`} type="number" min="0" disabled={product.is_sold_out} value={quantities[product.id] ?? 0} onChange={(event) => setQuantities({ ...quantities, [product.id]: Math.max(0, Math.floor(Number(event.target.value) || 0)) })} /></div>)}</div>{visibleProducts.length === 0 && <div className="staff-empty">このカテゴリの商品はありません</div>}<button className="staff-primary wide" disabled={selectedCount === 0} onClick={submitOrder}>選択した商品を注文（{selectedCount}点）</button></main>
  return <main className="staff-main"><header className="staff-heading"><div><small>STAFF</small><h1>テーブル状況</h1></div><button onClick={load}>更新</button></header>{message && <p className="staff-alert success">{message}</p>}{error && <p className="staff-alert error">{error}</p>}<div className="staff-table-grid">{tables.map((table) => <article className={table.is_in_use ? 'in-use' : 'available'} key={table.id}><header><h2>{table.table_name}</h2><span>{table.is_in_use ? '利用中' : '未利用'}</span></header>{table.active_session ? <><p>Session #{table.active_session.id}<br /><small>開始 {new Date(table.active_session.started_at).toLocaleString('ja-JP')}</small></p><div className="staff-actions"><button onClick={() => openOrder(table)}>代理注文</button><a className="complete" href={`/staff/accounting/${table.active_session.id}`}>会計確認</a></div></> : <button className="staff-primary" onClick={() => act(`/tables/${table.id}/sessions`, '利用を開始しました')}>利用開始</button>}</article>)}</div></main>
}
