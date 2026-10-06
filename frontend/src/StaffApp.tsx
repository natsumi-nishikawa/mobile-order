import StaffAccounting from './StaffAccounting'
import StaffMenu from './StaffMenu'
import StaffNav from './StaffNav'
import StaffOrders from './StaffOrders'
import StaffTables from './StaffTables'

export default function StaffApp() {
  const path = window.location.pathname
  const accountingMatch = path.match(/^\/staff\/accounting\/(\d+)$/)
  const screen = accountingMatch ? <StaffAccounting sessionId={Number(accountingMatch[1])} /> : path === '/staff/orders' ? <StaffOrders /> : path === '/staff/tables' ? <StaffTables /> : <StaffMenu />
  return <div className="staff-shell"><StaffNav />{screen}</div>
}
