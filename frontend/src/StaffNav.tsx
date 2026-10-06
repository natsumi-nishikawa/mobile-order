import './StaffCommon.css'
import { logoutStore } from './storeAuth'

export default function StaffNav() {
  const path = window.location.pathname
  return <nav className="staff-nav" aria-label="スタッフメニュー">
    <a className="staff-brand" href="/staff">MOBILE ORDER <strong>STAFF</strong></a>
    <div><a className={path === '/staff' || path === '/staff/tables' ? 'active' : ''} href="/staff/tables">テーブル</a><a className={path === '/staff/orders' ? 'active' : ''} href="/staff/orders">注文</a><button className="staff-logout" onClick={logoutStore}>ログアウト</button></div>
  </nav>
}
