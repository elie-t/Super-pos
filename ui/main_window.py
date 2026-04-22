"""
Main application window — hosts the login screen, then the back-office shell.
Each module is loaded on first access and cached.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QStackedWidget, QFrame,
)
from PySide6.QtCore import Qt, QSize

from ui.styles import APP_STYLE
from ui.screens.login_screen import LoginScreen
from ui.screens.dashboard_screen import DashboardScreen
from services.auth_service import AuthService


class HeaderBar(QFrame):
    def __init__(self, on_logout, on_dashboard, parent=None):
        super().__init__(parent)
        self.setObjectName("headerBar")
        self._on_logout   = on_logout
        self._on_dashboard = on_dashboard
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        home_btn = QPushButton("🏠  TannouryMarket")
        home_btn.setObjectName("headerTitle")
        home_btn.setStyleSheet(
            "QPushButton { background:transparent; border:none; "
            "font-size:17px; font-weight:700; color:#ffffff; padding:0; }"
            "QPushButton:hover { color:#f0c040; }"
        )
        home_btn.setCursor(Qt.PointingHandCursor)
        home_btn.clicked.connect(self._on_dashboard)
        layout.addWidget(home_btn)

        layout.addStretch()

        self.user_label = QLabel("")
        self.user_label.setObjectName("headerUser")
        layout.addWidget(self.user_label)

        self.role_label = QLabel("")
        self.role_label.setObjectName("headerRole")
        layout.addWidget(self.role_label)

        layout.addSpacing(12)

        logout_btn = QPushButton("Log Out")
        logout_btn.setStyleSheet(
            "QPushButton { background:#2a5a8c; color:#ffffff; border:1px solid #4a7aac; "
            "border-radius:4px; padding:4px 12px; font-size:12px; }"
            "QPushButton:hover { background:#1a4a7c; }"
        )
        logout_btn.setFixedHeight(28)
        logout_btn.setCursor(Qt.PointingHandCursor)
        logout_btn.clicked.connect(self._on_logout)
        layout.addWidget(logout_btn)

    def refresh_user(self):
        user = AuthService.current_user()
        if user:
            self.user_label.setText(f"{user.full_name}   ")
            self.role_label.setText(user.role.upper())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TannouryMarket — Retail Management")
        self.resize(1280, 800)
        self.setMinimumSize(QSize(1024, 640))
        self.setStyleSheet(APP_STYLE)
        self._modules: dict[str, QWidget] = {}
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = HeaderBar(
            on_logout=self._do_logout,
            on_dashboard=self._go_dashboard,
        )
        self._header.hide()
        root.addWidget(self._header)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._login_screen = LoginScreen()
        self._login_screen.login_successful.connect(self._on_login_success)
        self._stack.addWidget(self._login_screen)

        self._dashboard: DashboardScreen | None = None
        self.statusBar().showMessage("Ready")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_login_success(self):
        self._header.refresh_user()
        self._header.show()
        user = AuthService.current_user()

        if user and user.role == "cashier":
            # Cashiers go straight to POS with their assigned warehouse
            self._open_cashier_pos(user.warehouse_id)
            self.statusBar().showMessage(f"  POS  —  {user.full_name}")
            return

        # Admin / manager → full dashboard
        if self._dashboard is None:
            self._dashboard = DashboardScreen()
            self._dashboard.module_requested.connect(self._open_module)
            self._stack.addWidget(self._dashboard)
        self._stack.setCurrentWidget(self._dashboard)
        self.statusBar().showMessage(f"  {user.full_name}  [{user.role}]")

    def _open_cashier_pos(self, warehouse_id: str):
        """Open POS directly for cashier login, locked to their branch."""
        key = f"pos_{warehouse_id or 'default'}"
        if key not in self._modules:
            from ui.screens.pos.pos_screen import POSScreen
            w = POSScreen(forced_warehouse_id=warehouse_id or None)
            w.back.connect(self._do_logout)   # cashier "back" = logout
            self._modules[key] = w
            self._stack.addWidget(w)
        self._stack.setCurrentWidget(self._modules[key])

    def _go_dashboard(self):
        if self._dashboard:
            self._stack.setCurrentWidget(self._dashboard)
            self.statusBar().showMessage("Dashboard")

    def refresh_login(self):
        """Called by sync worker when users change — always refresh login buttons."""
        self._login_screen.refresh()

    def _do_logout(self):
        AuthService.logout()
        self._header.hide()
        self._stack.setCurrentIndex(0)
        self._login_screen.refresh()   # reload user buttons
        self.statusBar().showMessage("Logged out.")

    def _open_module(self, key: str):
        if key not in self._modules:
            widget = self._build_module(key)
            if widget is None:
                return
            self._modules[key] = widget
            self._stack.addWidget(widget)
        self._stack.setCurrentWidget(self._modules[key])
        self.statusBar().showMessage(f"  {key.capitalize()} module")

    def _build_module(self, key: str) -> QWidget | None:
        if key == "stock":
            from ui.screens.stock.stock_module import StockModule
            return StockModule()
        if key == "purchase":
            from ui.screens.purchase.purchase_module import PurchaseModule
            return PurchaseModule()
        if key == "pos":
            from ui.screens.pos.pos_screen import POSScreen
            w = POSScreen()
            w.back.connect(self._go_dashboard)
            return w
        if key == "sales":
            from ui.screens.sales.sales_module import SalesModule
            w = SalesModule()
            w.back.connect(self._go_dashboard)
            return w
        if key == "customers":
            from ui.screens.sales.customer_screen import CustomerScreen
            w = CustomerScreen()
            w.back.connect(self._go_dashboard)
            return w
        if key == "users":
            from ui.screens.admin.user_management import UserManagementScreen
            w = UserManagementScreen()
            w.back.connect(self._go_dashboard)
            # Refresh login screen buttons when users are changed
            w.back.connect(self._login_screen.refresh)
            return w
        if key == "settings":
            from ui.screens.settings.settings_screen import SettingsScreen
            w = SettingsScreen()
            w.back.connect(self._go_dashboard)
            return w
        if key == "suppliers":
            from ui.screens.purchase.supplier_list import SupplierListScreen
            w = SupplierListScreen()
            w.back.connect(self._go_dashboard)
            return w
        if key == "app_manager":
            from ui.screens.app.app_manager_screen import AppManagerScreen
            w = AppManagerScreen()
            w.back.connect(self._go_dashboard)
            return w
        # Other modules: placeholder until built
        w = QWidget()
        from PySide6.QtWidgets import QVBoxLayout as VL
        vl = VL(w)
        lbl = QLabel(f"{key.capitalize()} module — coming soon")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-size:20px; color:#888; margin:60px;")
        back = QPushButton("← Dashboard")
        back.setObjectName("secondaryBtn")
        back.setFixedWidth(140)
        back.clicked.connect(self._go_dashboard)
        vl.addWidget(back)
        vl.addWidget(lbl)
        return w
