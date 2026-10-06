import AdminAccounting from './AdminAccounting'
import AdminBusinessHours from './AdminBusinessHours'
import AdminCategories from './AdminCategories'
import AdminMenu from './AdminMenu'
import AdminNav from './AdminNav'
import AdminProducts from './AdminProducts'
import AdminTables from './AdminTables'
import AdminStaffUsers from './AdminStaffUsers'

export default function AdminApp() {
  const path = window.location.pathname
  let screen = <AdminMenu />
  if (path === '/admin/products') screen = <AdminProducts />
  else if (path === '/admin/categories') screen = <AdminCategories />
  else if (path === '/admin/tables') screen = <AdminTables />
  else if (path === '/admin/business-hours') screen = <AdminBusinessHours />
  else if (path === '/admin/accounting' || path.startsWith('/admin/accounting/')) screen = <AdminAccounting />
  else if (path === '/admin/staff-users') screen = <AdminStaffUsers />
  return <div className="admin-shell"><AdminNav />{screen}</div>
}
