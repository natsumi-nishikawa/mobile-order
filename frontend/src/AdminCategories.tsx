import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ADMIN_API, apiError } from './adminApi'
import type { Category } from './adminApi'

export default function AdminCategories() {
  const [items, setItems] = useState<Category[]>([])
  const [editing, setEditing] = useState<Category | 'new' | null>(null)
  const [name, setName] = useState('')
  const [displayOrder, setDisplayOrder] = useState('0')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const load = async () => { const response = await fetch(`${ADMIN_API}/categories`); if (response.ok) setItems(await response.json()); else setError(await apiError(response, 'カテゴリを取得できませんでした')) }
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [])
  const start = (item?: Category) => { setEditing(item ?? 'new'); setName(item?.name ?? ''); setDisplayOrder(String(item?.display_order ?? items.length)); setError(''); setMessage('') }
  const save = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    const order = Number(displayOrder)
    if (!name.trim() || !Number.isInteger(order) || order < 0) { setError('カテゴリ名と0以上の表示順を入力してください'); return }
    const isNew = editing === 'new'
    const response = await fetch(`${ADMIN_API}/categories${isNew ? '' : `/${editing!.id}`}`, { method: isNew ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim(), display_order: order }) })
    if (!response.ok) { setError(await apiError(response, '保存できませんでした')); return }
    setEditing(null); setMessage(isNew ? 'カテゴリを追加しました' : 'カテゴリを更新しました'); await load()
  }
  const remove = async (item: Category) => {
    if (!window.confirm(`「${item.name}」を削除しますか？`)) return
    const response = await fetch(`${ADMIN_API}/categories/${item.id}`, { method: 'DELETE' })
    if (!response.ok) { setError(await apiError(response, '削除できませんでした')); return }
    setMessage('カテゴリを削除しました'); setError(''); await load()
  }
  if (editing) return <main className="admin-app"><button className="admin-back" onClick={() => setEditing(null)}>← 一覧へ戻る</button><h1>{editing === 'new' ? 'カテゴリを追加' : 'カテゴリを編集'}</h1><form className="admin-form" onSubmit={save}><label>カテゴリ名<span>必須</span><input value={name} maxLength={100} onChange={(event) => setName(event.target.value)} /></label><label>表示順<span>必須</span><input type="number" min="0" step="1" value={displayOrder} onChange={(event) => setDisplayOrder(event.target.value)} /></label>{error && <p className="admin-error">{error}</p>}<button className="admin-primary">保存する</button></form></main>
  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>カテゴリ管理</h1></div><button className="admin-primary" onClick={() => start()}>カテゴリを追加</button></header>{message && <p className="admin-success">{message}</p>}{error && <p className="admin-error">{error}</p>}<div className="admin-table-wrap"><table><thead><tr><th>表示順</th><th>カテゴリ名</th><th>操作</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.display_order}</td><td><strong>{item.name}</strong></td><td className="actions"><button onClick={() => start(item)}>編集</button><button className="danger" onClick={() => remove(item)}>削除</button></td></tr>)}</tbody></table>{items.length === 0 && <div className="admin-empty">カテゴリが登録されていません</div>}</div></main>
}
