"""
Login screen — shows active user buttons; clicking a name prompts for password.
Admin logs in to the full back-office; cashiers go directly to POS.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QDialog,
    QDialogButtonBox, QScrollArea, QGridLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from services.auth_service import AuthService


# ── Password prompt dialog ────────────────────────────────────────────────────

class _PasswordDialog(QDialog):
    def __init__(self, full_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Password")
        self.setFixedWidth(340)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 30, 30, 24)
        lay.setSpacing(14)

        name_lbl = QLabel(full_name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet(
            "font-size:17px;font-weight:700;color:#1a3a5c;"
        )
        lay.addWidget(name_lbl)

        hint = QLabel("Enter your password to log in")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:12px;color:#6b7a8d;")
        lay.addWidget(hint)

        lay.addSpacing(4)

        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.Password)
        self._pw.setPlaceholderText("Password")
        self._pw.setFixedHeight(42)
        self._pw.setStyleSheet(
            "QLineEdit{border:2px solid #b0bec5;border-radius:6px;"
            "padding:0 10px;font-size:14px;color:#1a1a2e;}"
            "QLineEdit:focus{border-color:#1a6cb5;}"
        )
        lay.addWidget(self._pw)

        self._err = QLabel("")
        self._err.setAlignment(Qt.AlignCenter)
        self._err.setStyleSheet("color:#c62828;font-size:12px;")
        self._err.hide()
        lay.addWidget(self._err)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(36)
        cancel.setStyleSheet(
            "QPushButton{background:#eceff1;color:#37474f;border:none;"
            "border-radius:5px;font-size:13px;}"
            "QPushButton:hover{background:#cfd8dc;}"
        )
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        self._ok = QPushButton("Log In")
        self._ok.setFixedHeight(36)
        self._ok.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        self._ok.clicked.connect(self._submit)
        btn_row.addWidget(self._ok)
        lay.addLayout(btn_row)

        self._pw.returnPressed.connect(self._submit)
        self._pw.setFocus()

    def _submit(self):
        if not self._pw.text():
            self._show_err("Please enter your password.")
            return
        self.accept()

    def _show_err(self, msg: str):
        self._err.setText(msg)
        self._err.show()
        self._pw.clear()
        self._pw.setFocus()

    def show_error(self, msg: str):
        self._show_err(msg)

    def password(self) -> str:
        return self._pw.text()


# ── Login screen ──────────────────────────────────────────────────────────────

class LoginScreen(QWidget):
    """
    Shows all active users as name buttons.
    Emits `login_successful` after authentication.
    Parent reads AuthService.current_user().role to decide where to navigate.
    """
    login_successful = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setAlignment(Qt.AlignCenter)

        # Outer card
        card = QFrame()
        card.setObjectName("loginCard")
        card.setMinimumWidth(560)
        card.setMaximumWidth(760)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(40, 36, 40, 36)
        card_lay.setSpacing(0)

        # Title
        title = QLabel("TannouryMarket")
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(title)

        subtitle = QLabel("Retail Management System")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(subtitle)

        card_lay.addSpacing(28)

        who = QLabel("WHO IS LOGGING IN?")
        who.setObjectName("loginLabel")
        who.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(who)

        card_lay.addSpacing(14)

        # Scrollable user button grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMaximumHeight(520)

        self._btn_container = QWidget()
        self._grid = QGridLayout(self._btn_container)
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._btn_container)
        card_lay.addWidget(scroll)

        card_lay.addSpacing(10)

        self._status = QLabel("")
        self._status.setObjectName("errorLabel")
        self._status.setAlignment(Qt.AlignCenter)
        self._status.hide()
        card_lay.addWidget(self._status)

        card_lay.addSpacing(12)

        ver = QLabel("v1.0.0")
        ver.setObjectName("appSubtitle")
        ver.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(ver)

        root.addWidget(card, alignment=Qt.AlignCenter)

        self._load_users()

    def _load_users(self):
        """Populate the grid with one button per active user."""
        # Clear old buttons
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        users = self._fetch_active_users()
        if not users:
            lbl = QLabel("No users found on this device.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#888;font-size:13px;")
            self._grid.addWidget(lbl, 0, 0, 1, 3)
            btn = QPushButton("⬇  Pull Users from Server")
            btn.setFixedSize(220, 44)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{background:#1a3a5c;color:#fff;border:none;"
                "border-radius:8px;font-size:13px;font-weight:700;}"
                "QPushButton:hover{background:#1a6cb5;}"
            )
            btn.clicked.connect(self._pull_users_from_server)
            self._grid.addWidget(btn, 1, 0, 1, 3, Qt.AlignCenter)
            return

        COLS = 3
        for idx, (uid, username, full_name, role) in enumerate(users):
            btn = QPushButton(full_name)
            btn.setFixedSize(160, 70)
            btn.setCursor(Qt.PointingHandCursor)
            is_admin = role in ("admin", "manager")
            if is_admin:
                btn.setStyleSheet(
                    "QPushButton{background:#1a3a5c;color:#fff;border:none;"
                    "border-radius:8px;font-size:14px;font-weight:700;}"
                    "QPushButton:hover{background:#1a6cb5;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#e8f0fb;color:#1a3a5c;border:2px solid #b0c4de;"
                    "border-radius:8px;font-size:14px;font-weight:600;}"
                    "QPushButton:hover{background:#1a3a5c;color:#fff;border-color:#1a3a5c;}"
                )
            btn.clicked.connect(
                lambda _=False, u=username, n=full_name: self._on_user_clicked(u, n)
            )
            row, col = divmod(idx, COLS)
            self._grid.addWidget(btn, row, col, Qt.AlignCenter)

    def _pull_users_from_server(self):
        from sync.service import pull_users, is_configured
        if not is_configured():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Not Configured",
                                "Supabase is not configured. Check your .env file.")
            return
        count, err = pull_users()
        if err:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to pull users:\n{err}")
        else:
            self._refresh_user_grid()

    def _fetch_active_users(self) -> list[tuple]:
        """Returns list of (id, username, full_name, role) for all active users."""
        from database.engine import get_session, init_db
        from database.models.users import User
        init_db()
        session = get_session()
        try:
            users = (
                session.query(User)
                .filter_by(is_active=True)
                .order_by(User.full_name)
                .all()
            )
            return [(u.id, u.username, u.full_name, u.role) for u in users]
        finally:
            session.close()

    # ── Interaction ───────────────────────────────────────────────────────────

    def _on_user_clicked(self, username: str, full_name: str):
        dlg = _PasswordDialog(full_name, self)
        while True:
            if dlg.exec() != QDialog.Accepted:
                return
            pw = dlg.password()
            success, error = AuthService.login(username, pw)
            if success:
                self._status.hide()
                self.login_successful.emit()
                return
            dlg.show_error(error or "Incorrect password.")

    def refresh(self):
        """Reload user buttons — call after user management changes."""
        self._load_users()
