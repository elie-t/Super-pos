"""
Back-office dashboard — main hub after login.
Shows module tiles and operator info.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QFrame, QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from config import IS_MAIN_BRANCH
from services.auth_service import AuthService


# (icon_text, title, subtitle, module_key, admin_only, main_only)
DASHBOARD_TILES = [
    ("🛒", "Purchase",    "Suppliers & invoices",   "purchase",    False, True),
    ("🧾", "Sales",       "Invoices & receipts",    "sales",       False, False),
    ("🖥️", "POS",         "Fast cashier screen",    "pos",         False, False),
    ("📦", "Stock",       "Items & movements",      "stock",       False, True),
    ("👥", "Customers",   "Client management",      "customers",   False, False),
    ("🏭", "Suppliers",   "Supplier management",    "suppliers",   False, True),
    ("📊", "Reports",     "Sales & stock reports",  "reports",     False, False),
    ("💰", "Financials",  "Payments & balances",    "financials",  False, False),
    ("⚙️", "Settings",    "System configuration",   "settings",    False, False),
    ("📱", "App Manager", "Mobile app control",     "app_manager", False, True),
    ("👤", "Users",       "Manage cashier accounts","users",       True,  False),
]


class DashboardTile(QPushButton):
    """A clickable module tile. Uses QPushButton so clicks work natively."""

    def __init__(self, icon: str, title: str, subtitle: str, key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("dashTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(180, 140)
        self._key = key

        # QPushButton doesn't support layouts directly with child widgets easily,
        # so we embed a QWidget inside it
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        icon_lbl = QLabel(icon)
        icon_lbl.setObjectName("tileIcon")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("tileTitle")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setObjectName("tileLabel")
        sub_lbl.setAlignment(Qt.AlignCenter)
        sub_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(sub_lbl)


class DashboardScreen(QWidget):
    module_requested = Signal(str)   # parent connects this to navigate

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 24, 30, 24)
        root.setSpacing(20)

        # ── Welcome header ────────────────────────────────────────────────────
        user = AuthService.current_user()
        name = user.full_name if user else "Operator"
        role = user.role.capitalize() if user else ""

        hdr = QHBoxLayout()
        welcome = QLabel(f"Welcome, {name}")
        welcome.setStyleSheet("font-size: 20px; font-weight: 600; color: #1a3a5c;")
        role_badge = QLabel(role)
        role_badge.setObjectName("headerRole")
        role_badge.setFixedHeight(24)
        hdr.addWidget(welcome)
        hdr.addStretch()
        hdr.addWidget(role_badge)
        root.addLayout(hdr)

        section = QLabel("SELECT A MODULE")
        section.setObjectName("sidebarSection")
        section.setContentsMargins(0, 0, 0, 0)
        root.addWidget(section)

        # ── Tile grid ─────────────────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        is_admin = user and user.role in ("admin", "manager")
        visible_tiles = [
            t for t in DASHBOARD_TILES
            if (not t[4] or is_admin) and (not t[5] or IS_MAIN_BRANCH)
        ]
        for i, (icon, title, subtitle, key, _admin, _main) in enumerate(visible_tiles):
            tile = DashboardTile(icon, title, subtitle, key)
            tile.clicked.connect(lambda checked=False, k=key: self.module_requested.emit(k))
            row, col = divmod(i, 5)
            grid.addWidget(tile, row, col)

        root.addLayout(grid)
        root.addStretch()

        # ── Sync bar (admin only) ──────────────────────────────────────────────
        if is_admin:
            from sync.service import is_configured
            sync_bar = QHBoxLayout()
            self._sync_lbl = QLabel("")
            self._sync_lbl.setStyleSheet("font-size:11px;color:#2e7d32;font-weight:600;")
            sync_bar.addWidget(self._sync_lbl)
            sync_bar.addStretch()
            if is_configured() and IS_MAIN_BRANCH:
                sync_btn = QPushButton("☁  Sync Online Catalog Now")
                sync_btn.setFixedHeight(28)
                sync_btn.setStyleSheet(
                    "QPushButton{background:#1a3a5c;color:#fff;border:none;"
                    "border-radius:4px;font-size:12px;font-weight:700;padding:0 14px;}"
                    "QPushButton:hover{background:#1a6cb5;}"
                )
                sync_btn.setCursor(Qt.PointingHandCursor)
                sync_btn.clicked.connect(self._do_sync)
                sync_bar.addWidget(sync_btn)
            root.addLayout(sync_bar)

        # ── Bottom stats bar ──────────────────────────────────────────────────
        self._stats_bar = QLabel("Loading stats…")
        self._stats_bar.setStyleSheet("color: #5a6070; font-size: 11px;")
        root.addWidget(self._stats_bar)
        self._load_stats()

    def _do_sync(self):
        self._sync_lbl.setText("Syncing…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        from sync.push_all import push_all_online_items
        ok, fail, errors = push_all_online_items()
        if fail == 0:
            self._sync_lbl.setText(f"✓  {ok} items synced to online catalog")
            self._sync_lbl.setStyleSheet("font-size:11px;color:#2e7d32;font-weight:600;")
        else:
            self._sync_lbl.setText(f"⚠  {ok} synced, {fail} failed: {errors[0] if errors else ''}")
            self._sync_lbl.setStyleSheet("font-size:11px;color:#c62828;font-weight:600;")

    def _load_stats(self):
        from database.engine import get_session, init_db
        from database.models.items import Item
        from database.models.parties import Supplier, Customer
        init_db()
        session = get_session()
        try:
            items     = session.query(Item).filter_by(is_active=True).count()
            suppliers = session.query(Supplier).filter_by(is_active=True).count()
            customers = session.query(Customer).filter_by(is_active=True).count()
            self._stats_bar.setText(
                f"  Items: {items:,}   |   Suppliers: {suppliers:,}   |   Customers: {customers:,}"
            )
        finally:
            session.close()
