import { useEffect, useState } from 'react'
import { CUSTOMER_API, loginDemo, protectedFetch } from './demoAuth'

export type DemoTable = { id: number; table_name: string; is_in_use: boolean }

export function DemoLogin({ onAuthenticated, initialError = '' }: { onAuthenticated: () => void; initialError?: string }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState(initialError)
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!password || submitting) return
    setSubmitting(true); setError('')
    try {
      await loginDemo(password)
      setPassword('')
      onAuthenticated()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'デモ認証に失敗しました')
    } finally { setSubmitting(false) }
  }

  return <main className="app entry demo-entry"><div className="brand">MOBILE ORDER</div><h1>社内デモ</h1><section className="panel"><label htmlFor="demo-password">共通パスワード</label><input id="demo-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void submit() }} autoComplete="current-password" autoFocus /><button className="primary" disabled={submitting || !password} onClick={() => void submit()}>{submitting ? '認証中...' : 'ログイン'}</button>{error && <p className="error-text" role="alert">{error}</p>}</section></main>
}

export function UserChooser({ onCustomer, onStaff, onAdmin, onLogout, error }: { onCustomer: () => void; onStaff: () => void; onAdmin: () => void; onLogout: () => void; error?: string }) {
  return <main className="app entry demo-entry"><div className="brand">MOBILE ORDER</div><h1>利用者を選択</h1>{error && <div className="notice error" role="alert">{error}</div>}<section className="panel role-buttons"><button className="primary" onClick={onCustomer}>お客様</button><button onClick={onStaff}>スタッフ</button><button onClick={onAdmin}>管理者</button></section><button className="text-button" onClick={onLogout}>デモからログアウト</button></main>
}

export function CustomerTableChooser({ onSelect, onBack }: { onSelect: (table: DemoTable) => void; onBack: () => void }) {
  const [tables, setTables] = useState<DemoTable[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    protectedFetch(`${CUSTOMER_API}/tables`).then(async (response) => {
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? 'テーブル一覧を取得できませんでした')
      setTables(await response.json())
    }).catch((reason) => setError(reason instanceof Error ? reason.message : '通信に失敗しました')).finally(() => setLoading(false))
  }, [])

  return <main className="app entry demo-entry table-entry"><button className="back" onClick={onBack}>← 利用者選択へ</button><div className="brand">MOBILE ORDER</div><h1>テーブルを選択</h1>{loading ? <p>読み込み中...</p> : error ? <div className="notice error">{error}</div> : <div className="table-choice-list">{tables.map((table) => <button key={table.id} disabled={!table.is_in_use} onClick={() => onSelect(table)}><span>{table.table_name}</span><small>{table.is_in_use ? '利用中・選択できます' : '未利用・選択できません'}</small></button>)}</div>}</main>
}
