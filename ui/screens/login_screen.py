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


# ── Password prompt dialog (with touch numpad) ────────────────────────────────

class _PasswordDialog(QDialog):
    def __init__(self, full_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Password")
        self.setFixedWidth(320)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(10)

        name_lbl = QLabel(full_name)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("font-size:17px;font-weight:700;color:#1a3a5c;")
        lay.addWidget(name_lbl)

        hint = QLabel("Enter your password")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size:11px;color:#6b7a8d;")
        lay.addWidget(hint)

        # Password field (keyboard + numpad both feed here)
        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.Password)
        self._pw.setPlaceholderText("Password / PIN")
        self._pw.setFixedHeight(44)
        self._pw.setAlignment(Qt.AlignCenter)
        self._pw.setStyleSheet(
            "QLineEdit{border:2px solid #b0bec5;border-radius:6px;"
            "padding:0 10px;font-size:18px;letter-spacing:4px;color:#1a1a2e;}"
            "QLineEdit:focus{border-color:#1a6cb5;}"
        )
        self._pw.returnPressed.connect(self._submit)
        lay.addWidget(self._pw)

        self._err = QLabel("")
        self._err.setAlignment(Qt.AlignCenter)
        self._err.setStyleSheet("color:#c62828;font-size:11px;")
        self._err.hide()
        lay.addWidget(self._err)

        # ── Numpad ────────────────────────────────────────────────────────────
        pad = QGridLayout()
        pad.setSpacing(8)

        def _nstyle(bg="#f5f7fa", fg="#1a3a5c"):
            return (
                f"QPushButton{{background:{bg};color:{fg};border:1px solid #cfd8dc;"
                f"border-radius:8px;font-size:20px;font-weight:700;}}"
                f"QPushButton:hover{{background:#dce6f5;}}"
                f"QPushButton:pressed{{background:#b0c4de;}}"
            )

        keys = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            ("⌫",  3, 0), ("0", 3, 1), ("OK", 3, 2),
        ]
        for label, r, c in keys:
            btn = QPushButton(label)
            btn.setFixedHeight(58)
            btn.setCursor(Qt.PointingHandCursor)
            if label == "OK":
                btn.setStyleSheet(_nstyle("#1a3a5c", "#fff"))
                btn.clicked.connect(self._submit)
            elif label == "⌫":
                btn.setStyleSheet(_nstyle("#fff3e0", "#e65100"))
                btn.clicked.connect(self._backspace)
            else:
                btn.setStyleSheet(_nstyle())
                btn.clicked.connect(lambda _, d=label: self._append(d))
            pad.addWidget(btn, r, c)

        lay.addLayout(pad)

        # Cancel link at bottom
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(32)
        cancel.setStyleSheet(
            "QPushButton{background:transparent;color:#90a4ae;border:none;font-size:12px;}"
            "QPushButton:hover{color:#546e7a;}"
        )
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel, alignment=Qt.AlignCenter)

        self._pw.setFocus()

    def _append(self, digit: str):
        self._pw.setText(self._pw.text() + digit)
        self._err.hide()

    def _backspace(self):
        self._pw.setText(self._pw.text()[:-1])

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
        from ui.main_window import _get_app_name
        from config import APP_MODE
        title = QLabel(_get_app_name())
        title.setObjectName("appTitle")
        title.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(title)

        subtitle = QLabel("Restaurant POS" if APP_MODE == "restaurant" else "Retail Management System")
        subtitle.setObjectName("appSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        card_lay.addWidget(subtitle)

        # Branch name badge
        card_lay.addSpacing(10)
        self._branch_lbl = QLabel("")
        self._branch_lbl.setAlignment(Qt.AlignCenter)
        self._branch_lbl.setStyleSheet(
            "background:#1b5e20;color:#fff;font-size:13px;font-weight:700;"
            "border-radius:6px;padding:5px 18px;"
        )
        self._branch_lbl.setFixedHeight(32)
        card_lay.addWidget(self._branch_lbl, alignment=Qt.AlignCenter)
        self._refresh_branch_badge()

        card_lay.addSpacing(20)

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

    def _refresh_branch_badge(self):
        branch_name = self._get_branch_name()
        if branch_name:
            self._branch_lbl.setText(f"📍  {branch_name}")
            self._branch_lbl.show()
        else:
            self._branch_lbl.hide()

    def _pull_users_from_server(self):
        from sync.service import pull_users, pull_warehouses, is_configured
        if not is_configured():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Not Configured",
                                "Supabase is not configured. Check your .env file.")
            return
        # Pull warehouses first so branch name shows and FK constraints are satisfied
        pull_warehouses()
        count, err = pull_users()
        if err:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", f"Failed to pull users:\n{err}")
        else:
            self._refresh_branch_badge()
            self._load_users()

    def _get_branch_name(self) -> str:
        """Return the warehouse name for this branch, or '' if not found."""
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            branch_id = os.getenv("BRANCH_ID", "")
            if not branch_id:
                return ""
            from database.engine import get_session, init_db
            import sqlalchemy as sa
            init_db()
            session = get_session()
            try:
                row = session.execute(
                    sa.text("SELECT name FROM warehouses WHERE id=:id"),
                    {"id": branch_id}
                ).fetchone()
                return row[0] if row else ""
            finally:
                session.close()
        except Exception:
            return ""

    def _fetch_active_users(self) -> list[tuple]:
        """Returns active users for this branch: branch cashiers + all admins/managers."""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        branch_id = os.getenv("BRANCH_ID", "")

        from database.engine import get_session, init_db
        from database.models.users import User
        import sqlalchemy as sa
        init_db()
        session = get_session()
        try:
            q = session.query(User).filter_by(is_active=True)
            if branch_id:
                # Show users assigned to this branch OR admins/managers (any branch)
                q = q.filter(
                    sa.or_(
                        User.warehouse_id == branch_id,
                        User.role.in_(["admin", "manager"]),
                        User.warehouse_id == None,   # unassigned users visible everywhere
                    )
                )
            users = q.order_by(
                # Admins first, then alphabetical
                sa.case({"admin": 0, "manager": 1}, value=User.role, else_=2),
                User.full_name
            ).all()
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
