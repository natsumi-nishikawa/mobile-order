const menuItems = [
  ['/admin/products', '商品管理', '商品の登録、編集、売り切れ、画像を管理'],
  ['/admin/categories', 'カテゴリ管理', 'カテゴリ名と表示順を管理'],
  ['/admin/tables', 'テーブル管理', '注文に使用するテーブルを管理'],
  ['/admin/business-hours', '営業時間管理', '曜日ごとの営業状態と時間を管理'],
  ['/admin/accounting', '会計履歴', '完了した会計の確認と取消'],
]

export default function AdminMenu() {
  return <main className="admin-app"><header className="admin-header"><div><small>ADMIN</small><h1>管理メニュー</h1></div></header>
    <div className="admin-menu-grid">{menuItems.map(([href, title, description]) =>
      <a className="admin-menu-item" href={href} key={href}><strong>{title}</strong><span>{description}</span><b aria-hidden="true">›</b></a>
    )}</div>
  </main>
}
