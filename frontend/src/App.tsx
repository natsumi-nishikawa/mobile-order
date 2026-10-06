import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import AdminApp from './AdminApp'
import StaffApp from './StaffApp'
import { StoreCallback, StoreGuard, StoreLogin } from './storeAuth'
import './StoreAuth.css'

const API_BASE = 'http://localhost:8000/api/customer'

type Screen = 'menu' | 'confirm' | 'complete' | 'history' | 'bill'
type Customer = { participant_id: number; session_id: number; table_id: number; table_name: string; nickname: string }
type Category = { id: number; name: string; display_order: number }
type Product = { id: number; name: string; price: number; description: string | null; image_url: string | null; is_sold_out: boolean; display_order: number | null; category_ids: number[] }
type Selection = { participant_id: number; nickname: string; product_id: number; product_name: string; quantity: number }
type OrderItem = { product_id: number; product_name: string; quantity: number; unit_price: number; canceled_quantity: number; served_quantity: number; effective_quantity: number; line_total: number; is_served: boolean }
type Order = { order_id: number; ordered_at: string; order_type: string; items: OrderItem[] }

const yen = (value: number) => `${value.toLocaleString('ja-JP')}円`

function CustomerApp() {
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [nickname, setNickname] = useState('')
  const [tableName, setTableName] = useState('')
  const [screen, setScreen] = useState<Screen>('menu')
  const [categories, setCategories] = useState<Category[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [selections, setSelections] = useState<Selection[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [billTotal, setBillTotal] = useState(0)
  const [splitCount, setSplitCount] = useState(1)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [unavailable, setUnavailable] = useState('')
  const [activeCategoryId, setActiveCategoryId] = useState<number | 'all'>('all')

  const tableId = useMemo(() => {
    const value = new URLSearchParams(window.location.search).get('table_id')
    const parsed = Number(value)
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null
  }, [])

  const authFetch = useCallback(async (path: string, options: RequestInit = {}) => {
    const token = localStorage.getItem('customer_token')
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
    if (response.status === 401) {
      localStorage.removeItem('customer_token')
      setCustomer(null)
      setUnavailable('利用情報が終了しました。QRコードから入り直してください。')
    }
    return response
  }, [])

  const loadMenu = useCallback(async (current: Customer) => {
    const [categoryResponse, productResponse, selectionResponse] = await Promise.all([
      authFetch('/categories'), authFetch('/products'), authFetch(`/sessions/${current.session_id}/selections`),
    ])
    if (!categoryResponse.ok || !productResponse.ok || !selectionResponse.ok) throw new Error('メニューを取得できませんでした')
    setCategories(await categoryResponse.json())
    setProducts(await productResponse.json())
    setSelections(await selectionResponse.json())
  }, [authFetch])

  useEffect(() => {
    const initialize = async () => {
      try {
        const token = localStorage.getItem('customer_token')
        if (token) {
          const response = await authFetch('/me')
          if (response.ok) {
            const me: Customer = await response.json()
            if (tableId !== null && me.table_id !== tableId) {
              localStorage.removeItem('customer_token')
            } else {
              setCustomer(me); setNickname(me.nickname); setTableName(me.table_name)
              await loadMenu(me)
              return
            }
          }
        }
        if (tableId === null) { setUnavailable('QRコードからアクセスしてください。'); return }
        const response = await fetch(`${API_BASE}/tables/${tableId}/session`)
        const data = await response.json().catch(() => ({}))
        if (!response.ok) { setUnavailable(data.detail ?? '現在利用できません'); return }
        setTableName(data.table_name)
      } catch { setUnavailable('通信に失敗しました。しばらくしてから再度お試しください。') }
      finally { setLoading(false) }
    }
    initialize().finally(() => setLoading(false))
  }, [authFetch, loadMenu, tableId])

  const showError = async (response: Response, fallback: string) => {
    const data = await response.json().catch(() => ({}))
    setMessage(data.detail ?? fallback)
  }

  const handleStart = async () => {
    const trimmed = nickname.trim()
    if (!trimmed || tableId === null) { setMessage('ニックネームを入力してください'); return }
    if (trimmed.length > 20) { setMessage('ニックネームは20文字以内で入力してください'); return }
    setSubmitting(true); setMessage('')
    try {
      const sessionResponse = await fetch(`${API_BASE}/tables/${tableId}/session`)
      const session = await sessionResponse.json().catch(() => ({}))
      if (!sessionResponse.ok) { setUnavailable(session.detail ?? '現在利用できません'); return }
      const response = await fetch(`${API_BASE}/sessions/${session.session_id}/participants`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ nickname: trimmed }) })
      if (!response.ok) { await showError(response, '登録に失敗しました'); return }
      const participant = await response.json()
      localStorage.setItem('customer_token', participant.access_token)
      const current = { participant_id: participant.participant_id, session_id: participant.session_id, table_id: tableId, table_name: session.table_name, nickname: participant.nickname }
      setCustomer(current); setNickname(current.nickname); setTableName(current.table_name)
      await loadMenu(current)
    } catch { setMessage('通信に失敗しました') }
    finally { setSubmitting(false) }
  }

  const myQuantity = (productId: number) => selections.find((item) => item.product_id === productId && item.participant_id === customer?.participant_id)?.quantity ?? 0
  const refreshSelections = async () => {
    if (!customer) return
    const response = await authFetch(`/sessions/${customer.session_id}/selections`)
    if (response.ok) setSelections(await response.json())
  }
  const changeQuantity = async (product: Product, quantity: number) => {
    if (!customer || product.is_sold_out) return
    setMessage('')
    const response = quantity <= 0
      ? await authFetch(`/selections/${product.id}`, { method: 'DELETE' })
      : await authFetch(`/selections/${product.id}`, { method: 'PUT', body: JSON.stringify({ quantity }) })
    if (!response.ok) { await showError(response, '選択を変更できませんでした'); return }
    await refreshSelections()
  }

  const mySelections = selections.filter((item) => item.participant_id === customer?.participant_id)
  const selectedProducts = mySelections.map((selection) => ({ selection, product: products.find((product) => product.id === selection.product_id)! })).filter((item) => item.product)
  const confirmTotal = selectedProducts.reduce((sum, item) => sum + item.product.price * item.selection.quantity, 0)
  const menuCategories = products.some((product) => product.category_ids.length === 0)
    ? [...categories, { id: 0, name: 'その他', display_order: Number.MAX_SAFE_INTEGER }]
    : categories
  const visibleProducts = activeCategoryId === 'all'
    ? products
    : products.filter((product) => activeCategoryId === 0 ? product.category_ids.length === 0 : product.category_ids.includes(activeCategoryId))
  const activeCategoryName = activeCategoryId === 'all'
    ? 'すべての商品'
    : menuCategories.find((category) => category.id === activeCategoryId)?.name ?? 'メニュー'

  const placeOrder = async () => {
    if (submitting) return
    setSubmitting(true); setMessage('')
    try {
      const response = await authFetch('/orders', { method: 'POST', body: '{}' })
      if (!response.ok) { await showError(response, '注文できませんでした'); return }
      await response.json(); setSelections([]); setScreen('complete')
    } finally { setSubmitting(false) }
  }

  const openHistory = async () => {
    if (!customer) return
    const response = await authFetch(`/sessions/${customer.session_id}/orders`)
    if (response.ok) { setOrders(await response.json()); setScreen('history') } else await showError(response, '注文履歴を取得できませんでした')
  }
  const openBill = async () => {
    if (!customer) return
    const response = await authFetch(`/sessions/${customer.session_id}/bill`)
    if (response.ok) { const data = await response.json(); setBillTotal(data.total_amount); setScreen('bill') } else await showError(response, '会計を取得できませんでした')
  }

  if (loading) return <main className="app"><p>読み込み中...</p></main>
  if (!customer) return <main className="app entry"><div className="brand">MOBILE ORDER</div><h1>{tableName || 'モバイルオーダー'}</h1>{unavailable ? <div className="notice error">{unavailable}</div> : <section className="panel"><label htmlFor="nickname">ニックネーム</label><input id="nickname" value={nickname} maxLength={20} onChange={(event) => setNickname(event.target.value)} placeholder="例：たろう" autoComplete="off" /><button className="primary" disabled={submitting} onClick={handleStart}>注文をはじめる</button>{message && <p className="error-text">{message}</p>}</section>}</main>

  return <div className="customer-shell">
    <aside className="customer-sidebar">
      <div className="sidebar-brand">MOBILE ORDER</div>
      <h2>メニュー</h2>
      <div className="sidebar-categories">
        <button className={screen === 'menu' && activeCategoryId === 'all' ? 'active' : ''} onClick={() => { setActiveCategoryId('all'); setScreen('menu') }}>すべて</button>
        {menuCategories.map((category) => <button key={category.id} className={screen === 'menu' && activeCategoryId === category.id ? 'active' : ''} onClick={() => { setActiveCategoryId(category.id); setScreen('menu') }}>{category.name}</button>)}
      </div>
      <div className="sidebar-links">
        <button className={screen === 'history' ? 'active' : ''} onClick={openHistory}>注文履歴</button>
        <button className={screen === 'bill' ? 'active' : ''} onClick={openBill}>お会計</button>
      </div>
    </aside>
    <main className="app customer-main">
    <header className="customer-header"><div><span className="table-name">{customer.table_name}</span><strong>{customer.nickname}さん</strong></div><button className="call" disabled>スタッフ呼び出し（準備中）</button></header>
    {message && <div className="notice error">{message}</div>}

    {screen === 'menu' && <>
      <div className="mobile-category-tabs">
        <button className={activeCategoryId === 'all' ? 'active' : ''} onClick={() => setActiveCategoryId('all')}>すべて</button>
        {menuCategories.map((category) => <button key={category.id} className={activeCategoryId === category.id ? 'active' : ''} onClick={() => setActiveCategoryId(category.id)}>{category.name}</button>)}
      </div>
      <div className="menu-title"><div><span>MENU</span><h1>{activeCategoryName}</h1></div><p>{visibleProducts.length}品</p></div>
      {visibleProducts.length === 0 ? <div className="empty-products">このカテゴリの商品はありません</div> : <div className="product-list">{visibleProducts.map((product) => {
        const quantity = myQuantity(product.id); const productSelections = selections.filter((item) => item.product_id === product.id); const total = productSelections.reduce((sum, item) => sum + item.quantity, 0)
        return <article className={`product ${product.is_sold_out ? 'sold-out' : ''}`} key={product.id}><div className="product-image">{product.image_url ? <img src={product.image_url} alt={product.name} /> : <div className="image-placeholder">NO IMAGE</div>}</div><div className="product-body"><div className="product-title"><h3>{product.name}</h3><strong>{yen(product.price)}</strong></div><p className="product-description">{product.description || '商品説明はありません'}</p><div className="product-status">{product.is_sold_out && <span className="badge">売り切れ</span>}{total > 0 && <p className="selection-info">{productSelections.length > 1 ? `みんなで${total}個選択中` : `${productSelections[0].nickname}さんが${total}個選択中`}</p>}</div><div className="stepper"><button aria-label={`${product.name}を減らす`} disabled={quantity === 0 || product.is_sold_out} onClick={() => changeQuantity(product, quantity - 1)}>−</button><span>{quantity}</span><button aria-label={`${product.name}を増やす`} disabled={product.is_sold_out} onClick={() => changeQuantity(product, quantity + 1)}>＋</button></div></div></article>
      })}</div>}
      <div className="bottom-space" /><nav className="customer-bottom-nav"><button onClick={openHistory}>注文履歴</button><button onClick={openBill}>会計</button><button className="primary" disabled={mySelections.length === 0} onClick={() => setScreen('confirm')}>注文する ({mySelections.reduce((sum, item) => sum + item.quantity, 0)})</button></nav>
    </>}

    {screen === 'confirm' && <section><button className="back" onClick={() => setScreen('menu')}>← メニューへ</button><h1>注文確認</h1><div className="panel">{selectedProducts.map(({ selection, product }) => <div className="line" key={product.id}><div><strong>{product.name}</strong><small>{yen(product.price)} × {selection.quantity}</small></div><strong>{yen(product.price * selection.quantity)}</strong></div>)}<div className="total"><span>合計</span><strong>{yen(confirmTotal)}</strong></div><button className="primary" disabled={submitting || selectedProducts.length === 0} onClick={placeOrder}>{submitting ? '注文中...' : '注文する'}</button></div></section>}

    {screen === 'complete' && <section className="center"><div className="complete-mark">✓</div><h1>注文を受け付けました</h1><p>商品が届くまでお待ちください。</p><button className="primary" onClick={() => setScreen('menu')}>メニューへ戻る</button><button onClick={openHistory}>注文履歴を見る</button></section>}

    {screen === 'history' && <section><button className="back" onClick={() => setScreen('menu')}>← メニューへ</button><h1>注文履歴</h1>{orders.length === 0 ? <div className="panel">注文はまだありません。</div> : orders.map((order) => <article className="panel order" key={order.order_id}><time>{new Date(order.ordered_at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })}</time>{order.items.map((item) => <div className="line" key={item.product_id}><div><strong>{item.product_name} ×{item.effective_quantity}</strong>{item.canceled_quantity > 0 && <small>{item.canceled_quantity}個キャンセル済み</small>}</div><span className={item.is_served ? 'served' : 'waiting'}>{item.is_served ? '提供済み' : '準備中'}</span></div>)}</article>)}</section>}

    {screen === 'bill' && <section><button className="back" onClick={() => setScreen('menu')}>← メニューへ</button><h1>会計</h1><div className="panel bill"><p>現在の合計金額</p><strong className="bill-total">{yen(billTotal)}</strong><label htmlFor="people">割り勘する人数</label><input id="people" type="number" min="1" step="1" value={splitCount} onChange={(event) => setSplitCount(Math.max(1, Math.floor(Number(event.target.value) || 1)))} /><div className="split"><span>1人あたり</span><strong>{yen(Math.ceil(billTotal / splitCount))}</strong></div><small>お支払いはスタッフへお願いします。</small></div></section>}
    </main>
  </div>
}

function App() {
  const params = new URLSearchParams(window.location.search)
  if (params.has('code') && params.has('state')) return <StoreCallback />
  if (window.location.pathname === '/login') return <StoreLogin />
  if (window.location.pathname.startsWith('/admin')) return <StoreGuard role="admin"><AdminApp /></StoreGuard>
  if (window.location.pathname.startsWith('/staff')) return <StoreGuard role="staff"><StaffApp /></StoreGuard>
  return <CustomerApp />
}

export default App
