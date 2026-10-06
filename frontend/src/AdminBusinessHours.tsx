import { useEffect, useState } from 'react'
import { ADMIN_API, apiError } from './adminApi'
import type { BusinessHour } from './adminApi'

const dayNames = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日']
const defaults = dayNames.map((_, day) => ({ day_of_week: day, is_open: true, opening_time: '09:00', closing_time: '22:00' }))
const timeValue = (value: string | null) => value?.slice(0, 5) ?? ''

export default function AdminBusinessHours() {
  const [items, setItems] = useState<BusinessHour[]>(defaults)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => { (async () => {
    const response = await fetch(`${ADMIN_API}/business-hours`)
    if (!response.ok) { setError(await apiError(response, '営業時間を取得できませんでした')); return }
    const existing: BusinessHour[] = await response.json()
    setItems(defaults.map((fallback) => existing.find((item) => item.day_of_week === fallback.day_of_week) ?? fallback))
  })() }, [])
  const update = (day: number, values: Partial<BusinessHour>) => setItems((current) => current.map((item) => item.day_of_week === day ? { ...item, ...values } : item))
  const save = async () => {
    setSaving(true); setError(''); setMessage('')
    const invalid = items.some((item) => item.is_open && (!item.opening_time || !item.closing_time || item.opening_time === item.closing_time))
    if (invalid) { setError('営業日は異なる開店時間と閉店時間を指定してください'); setSaving(false); return }
    const response = await fetch(`${ADMIN_API}/business-hours`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(items.map((item) => ({ day_of_week: item.day_of_week, is_open: item.is_open, opening_time: item.is_open ? timeValue(item.opening_time) : null, closing_time: item.is_open ? timeValue(item.closing_time) : null }))) })
    if (!response.ok) setError(await apiError(response, '営業時間を保存できませんでした'))
    else { setItems(await response.json()); setMessage('営業時間を保存しました') }
    setSaving(false)
  }
  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>営業時間管理</h1></div><button className="admin-primary" disabled={saving} onClick={save}>{saving ? '保存中...' : '変更を保存'}</button></header>{message && <p className="admin-success">{message}</p>}{error && <p className="admin-error">{error}</p>}<div className="business-hours-list">{items.map((item) => <section className="business-hour-row" key={item.day_of_week}><strong>{dayNames[item.day_of_week]}</strong><label className="admin-toggle"><input type="checkbox" checked={item.is_open} onChange={(event) => update(item.day_of_week, { is_open: event.target.checked })} /><span>{item.is_open ? '営業' : '休業'}</span></label><label>開店<input type="time" disabled={!item.is_open} value={timeValue(item.opening_time)} onChange={(event) => update(item.day_of_week, { opening_time: event.target.value })} /></label><label>閉店<input type="time" disabled={!item.is_open} value={timeValue(item.closing_time)} onChange={(event) => update(item.day_of_week, { closing_time: event.target.value })} /></label></section>)}</div></main>
}
