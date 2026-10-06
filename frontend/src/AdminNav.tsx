import './AdminCommon.css'
import { logoutStore } from './storeAuth'

const items = [
  ['/admin', '管理メニュー'],
  ['/admin/products', '商品管理'],
  ['/admin/categories', 'カテゴリ管理'],
  ['/admin/tables', 'テーブル管理'],
  ['/admin/business-hours', '営業時間管理'],
  ['/admin/accounting', '会計履歴'],
  ['/admin/staff-users', 'スタッフ管理'],
]

export default function AdminNav() {
  const path = window.location.pathname
  return <nav className="admin-nav" aria-label="管理画面メニュー">
    <a className="admin-nav-brand" href="/admin">MOBILE ORDER <strong>ADMIN</strong></a>
    <div className="admin-nav-links">{items.slice(1).map(([href, label]) =>
      <a key={href} className={path === href || path.startsWith(`${href}/`) ? 'active' : ''} href={href}>{label}</a>
    )}<button className="admin-logout" onClick={logoutStore}>ログアウト</button></div>
  </nav>
}
