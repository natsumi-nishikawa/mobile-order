import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ADMIN_API, adminFetch, apiError } from './adminApi'

type StaffUser = { username: string; email: string; display_name: string | null; enabled: boolean; status: string }

export default function AdminStaffUsers() {
  const [users, setUsers] = useState<StaffUser[]>([])
  const [creating, setCreating] = useState(false)
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const load = async () => { const response = await adminFetch(`${ADMIN_API}/staff-users`); if (response.ok) setUsers(await response.json()); else setError(await apiError(response, 'スタッフを取得できませんでした')) }
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { load() }, [])
  const create = async (event: FormEvent) => {
    event.preventDefault(); setError('')
    const response = await adminFetch(`${ADMIN_API}/staff-users`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, display_name: displayName || null, temporary_password: password }) })
    if (!response.ok) { setError(await apiError(response, 'スタッフを作成できませんでした')); return }
    setCreating(false); setEmail(''); setDisplayName(''); setPassword(''); setMessage('スタッフを作成し、staffグループへ追加しました'); await load()
  }
  const toggle = async (user: StaffUser) => {
    const action = user.enabled ? '無効化' : '有効化'
    if (!window.confirm(`${user.email}を${action}しますか？`)) return
    const response = await adminFetch(`${ADMIN_API}/staff-users/${encodeURIComponent(user.username)}/${user.enabled ? 'disable' : 'enable'}`, { method: 'POST' })
    if (!response.ok) { setError(await apiError(response, `${action}できませんでした`)); return }
    setMessage(`${action}しました`); await load()
  }
  const resetPassword = async (user: StaffUser) => {
    const temporaryPassword = window.prompt(`${user.email}の新しい一時パスワードを入力してください`)
    if (!temporaryPassword) return
    const response = await adminFetch(`${ADMIN_API}/staff-users/${encodeURIComponent(user.username)}/reset-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ temporary_password: temporaryPassword }) })
    if (!response.ok) { setError(await apiError(response, 'パスワードを再設定できませんでした')); return }
    setMessage('一時パスワードを設定しました。次回ログイン時に変更が必要です。')
  }
  if (creating) return <main className="admin-app"><button className="admin-back" onClick={() => setCreating(false)}>← 一覧へ戻る</button><h1>スタッフを作成</h1><form className="admin-form" onSubmit={create}><label>メールアドレス<span>必須</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label>表示名<input value={displayName} maxLength={100} onChange={(event) => setDisplayName(event.target.value)} /></label><label>初期パスワード<span>必須</span><input type="password" minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} required /></label><small>Cognitoのパスワードポリシーを満たす値を入力してください。</small>{error && <p className="admin-error">{error}</p>}<button className="admin-primary">作成する</button></form></main>
  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>スタッフ管理</h1></div><button className="admin-primary" onClick={() => { setCreating(true); setError('') }}>スタッフを追加</button></header>{message && <p className="admin-success">{message}</p>}{error && <p className="admin-error">{error}</p>}<div className="admin-table-wrap"><table><thead><tr><th>メールアドレス</th><th>表示名</th><th>状態</th><th>操作</th></tr></thead><tbody>{users.map((user) => <tr key={user.username}><td><strong>{user.email}</strong></td><td>{user.display_name || '—'}</td><td><span className={user.enabled ? 'staff-enabled' : 'staff-disabled'}>{user.enabled ? user.status : '無効'}</span></td><td className="actions"><button onClick={() => resetPassword(user)}>パスワード再設定</button><button className={user.enabled ? 'danger' : ''} onClick={() => toggle(user)}>{user.enabled ? '無効化' : '有効化'}</button></td></tr>)}</tbody></table>{users.length === 0 && <div className="admin-empty">staffグループのユーザーはいません</div>}</div></main>
}
