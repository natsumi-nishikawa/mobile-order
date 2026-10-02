import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './AdminProducts.css'

const ADMIN_API = 'http://localhost:8000/api/admin'

type Category = { id: number; name: string; display_order: number }
type Product = {
  id: number; name: string; price: number; description: string | null
  image_url: string | null; is_sold_out: boolean; display_order: number | null
  category_ids: number[]; category_names: string[]
}
type FormData = {
  name: string; price: string; description: string
  is_sold_out: boolean; display_order: string; category_ids: number[]
}

const emptyForm: FormData = { name: '', price: '', description: '', is_sold_out: false, display_order: '', category_ids: [] }

export default function AdminProducts() {
  const [products, setProducts] = useState<Product[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [editing, setEditing] = useState<Product | 'new' | null>(null)
  const [form, setForm] = useState<FormData>(emptyForm)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)

  const loadData = async () => {
    setLoading(true)
    try {
      const [productsResponse, categoriesResponse] = await Promise.all([
        fetch(`${ADMIN_API}/products`), fetch(`${ADMIN_API}/categories`),
      ])
      if (!productsResponse.ok || !categoriesResponse.ok) throw new Error()
      setProducts(await productsResponse.json())
      setCategories(await categoriesResponse.json())
    } catch { setError('商品情報を取得できませんでした') }
    finally { setLoading(false) }
  }

  // 初回表示時にバックエンドの商品・カテゴリを取得する
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { loadData() }, [])

  const clearPreview = () => {
    if (previewUrl?.startsWith('blob:')) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null); setImageFile(null)
  }
  const startNew = () => { clearPreview(); setEditing('new'); setForm(emptyForm); setError(''); setMessage('') }
  const startEdit = (product: Product) => {
    setEditing(product)
    clearPreview()
    setForm({ name: product.name, price: String(product.price), description: product.description ?? '', is_sold_out: product.is_sold_out, display_order: product.display_order === null ? '' : String(product.display_order), category_ids: product.category_ids })
    setPreviewUrl(product.image_url)
    setError(''); setMessage('')
  }
  const toggleCategory = (id: number) => setForm((current) => ({ ...current, category_ids: current.category_ids.includes(id) ? current.category_ids.filter((value) => value !== id) : [...current.category_ids, id] }))
  const selectImage = (file: File | undefined) => {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setError('jpg、jpeg、png、webp画像を選択してください'); return }
    if (file.size > 5 * 1024 * 1024) { setError('画像サイズは5MB以下にしてください'); return }
    if (previewUrl?.startsWith('blob:')) URL.revokeObjectURL(previewUrl)
    setImageFile(file); setPreviewUrl(URL.createObjectURL(file)); setError('')
  }

  const save = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setMessage('')
    const price = Number(form.price)
    const displayOrder = form.display_order === '' ? null : Number(form.display_order)
    if (!form.name.trim()) { setError('商品名を入力してください'); return }
    if (!Number.isInteger(price) || price < 0) { setError('価格は0以上の整数で入力してください'); return }
    if (displayOrder !== null && (!Number.isInteger(displayOrder) || displayOrder < 0)) { setError('表示順は0以上の整数で入力してください'); return }
    if (form.category_ids.length === 0) { setError('カテゴリを1つ以上選択してください'); return }
    setSaving(true)
    try {
      const isNew = editing === 'new'
      const response = await fetch(`${ADMIN_API}/products${isNew ? '' : `/${editing!.id}`}`, {
        method: isNew ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, name: form.name.trim(), price, display_order: displayOrder, description: form.description.trim() || null, image_url: null }),
      })
      if (!response.ok) { const data = await response.json().catch(() => ({})); setError(data.detail ?? '保存できませんでした'); return }
      const savedProduct: Product = await response.json()
      if (imageFile) {
        const imageData = new FormData()
        imageData.append('image', imageFile)
        const imageResponse = await fetch(`${ADMIN_API}/products/${savedProduct.id}/image`, { method: 'POST', body: imageData })
        if (!imageResponse.ok) { const data = await imageResponse.json().catch(() => ({})); setError(`商品情報は保存されましたが、画像を保存できませんでした：${data.detail ?? '画像アップロードエラー'}`); await loadData(); return }
      }
      clearPreview(); setEditing(null); setMessage(isNew ? '商品を登録しました' : '商品を更新しました'); await loadData()
    } catch { setError('通信に失敗しました') }
    finally { setSaving(false) }
  }

  const remove = async (product: Product) => {
    if (!window.confirm(`「${product.name}」を削除しますか？`)) return
    setError(''); setMessage('')
    const response = await fetch(`${ADMIN_API}/products/${product.id}`, { method: 'DELETE' })
    if (!response.ok) { const data = await response.json().catch(() => ({})); setError(data.detail ?? '削除できませんでした'); return }
    setMessage('商品を削除しました'); await loadData()
  }

  if (editing !== null) return <main className="admin-app">
    <button className="admin-back" onClick={() => { clearPreview(); setEditing(null) }}>← 商品一覧へ戻る</button>
    <h1>{editing === 'new' ? '商品を追加' : '商品を編集'}</h1>
    <form className="admin-form" onSubmit={save}>
      <label>商品名<span>必須</span><input value={form.name} maxLength={100} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label>価格<span>必須</span><input type="number" min="0" step="1" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></label>
      <fieldset><legend>カテゴリ<span>必須</span></legend>{categories.length === 0 ? <p className="admin-warning">カテゴリが登録されていないため、商品を保存できません。</p> : categories.map((category) => <label className="check" key={category.id}><input type="checkbox" checked={form.category_ids.includes(category.id)} onChange={() => toggleCategory(category.id)} />{category.name}</label>)}</fieldset>
      <label>商品説明<textarea rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
      <label>商品画像<small>（jpg・png・webp、5MB以下）</small><input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => selectImage(e.target.files?.[0])} /></label>
      {previewUrl && <div className="image-preview"><span>{imageFile ? '選択した画像' : '現在の画像'}</span><img src={previewUrl} alt="商品画像プレビュー" /></div>}
      <label>表示順<input type="number" min="0" step="1" value={form.display_order} onChange={(e) => setForm({ ...form, display_order: e.target.value })} /></label>
      <label className="switch"><input type="checkbox" checked={form.is_sold_out} onChange={(e) => setForm({ ...form, is_sold_out: e.target.checked })} />売り切れとして表示する</label>
      {error && <p className="admin-error">{error}</p>}
      <button className="admin-primary" disabled={saving || categories.length === 0}>{saving ? '保存中...' : editing === 'new' ? '登録する' : '変更を保存'}</button>
    </form>
  </main>

  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>商品管理</h1></div><button className="admin-primary" onClick={startNew}>＋ 商品を追加</button></header>
    {message && <p className="admin-success">{message}</p>}{error && <p className="admin-error">{error}</p>}
    {loading ? <p>読み込み中...</p> : products.length === 0 ? <div className="admin-empty">商品が登録されていません</div> : <div className="admin-table-wrap"><table><thead><tr><th>画像</th><th>商品名</th><th>価格</th><th>カテゴリ</th><th>状態</th><th>表示順</th><th>操作</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td>{product.image_url ? <img className="admin-thumb" src={product.image_url} alt="" /> : <span className="no-image">画像なし</span>}</td><td><strong>{product.name}</strong></td><td>{product.price.toLocaleString('ja-JP')}円</td><td>{product.category_names.join('、')}</td><td><span className={product.is_sold_out ? 'status sold' : 'status'}>{product.is_sold_out ? '売り切れ' : '販売中'}</span></td><td>{product.display_order ?? '未設定'}</td><td className="actions"><button onClick={() => startEdit(product)}>編集</button><button className="danger" onClick={() => remove(product)}>削除</button></td></tr>)}</tbody></table></div>}
  </main>
}
