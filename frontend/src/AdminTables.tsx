import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ADMIN_API, adminFetch, apiError } from './adminApi'
import type { DiningTable } from './adminApi'

export default function AdminTables() {
  const [items, setItems] = useState<DiningTable[]>([])
  const [editing, setEditing] = useState<DiningTable | 'new' | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const load = async () => { const response = await adminFetch(`${ADMIN_API}/tables`); if (response.ok) setItems(await response.json()); else setError(await apiError(response, 'テーブルを取得できませんでした')) }
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [])
  const save = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    if (!name.trim()) { setError('テーブル名を入力してください'); return }
    const isNew = editing === 'new'
    const response = await adminFetch(`${ADMIN_API}/tables${isNew ? '' : `/${editing!.id}`}`, { method: isNew ? 'POST' : 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ table_name: name.trim() }) })
    if (!response.ok) { setError(await apiError(response, '保存できませんでした')); return }
    setEditing(null); setMessage(isNew ? 'テーブルを追加しました' : 'テーブルを更新しました'); await load()
  }
  const remove = async (item: DiningTable) => {
    if (!window.confirm(`「${item.table_name}」を削除しますか？`)) return
    const response = await adminFetch(`${ADMIN_API}/tables/${item.id}`, { method: 'DELETE' })
    if (!response.ok) { setError(await apiError(response, '削除できませんでした')); return }
    setMessage('テーブルを削除しました'); setError(''); await load()
  }
  if (editing) return <main className="admin-app"><button className="admin-back" onClick={() => setEditing(null)}>← 一覧へ戻る</button><h1>{editing === 'new' ? 'テーブルを追加' : 'テーブルを編集'}</h1><form className="admin-form" onSubmit={save}><label>テーブル名<span>必須</span><input value={name} maxLength={100} onChange={(event) => setName(event.target.value)} /></label>{error && <p className="admin-error">{error}</p>}<button className="admin-primary">保存する</button></form></main>
  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>テーブル管理</h1></div><button className="admin-primary" onClick={() => { setEditing('new'); setName(''); setError('') }}>テーブルを追加</button></header>{message && <p className="admin-success">{message}</p>}{error && <p className="admin-error">{error}</p>}<div className="admin-table-wrap"><table><thead><tr><th>ID</th><th>テーブル名</th><th>操作</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.id}</td><td><strong>{item.table_name}</strong></td><td className="actions"><button onClick={() => { setEditing(item); setName(item.table_name); setError('') }}>編集</button><button className="danger" onClick={() => remove(item)}>削除</button></td></tr>)}</tbody></table>{items.length === 0 && <div className="admin-empty">テーブルが登録されていません</div>}</div></main>
}
