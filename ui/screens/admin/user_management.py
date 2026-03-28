"""
User Management screen — admin only.
Create / edit / deactivate cashier and admin accounts.
Each user can be assigned to a warehouse (branch) which the POS opens automatically.
"""
import bcrypt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QCheckBox,
    QFrame, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont


class UserManagementScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_users()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setFixedHeight(48)
        hdr.setStyleSheet("background:#1a3a5c;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 14, 0)

        back_btn = QPushButton("← Back")
        back_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#a8c8e8;border:none;font-size:13px;}"
            "QPushButton:hover{color:#fff;}"
        )
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back)
        hl.addWidget(back_btn)

        title = QLabel("👤  User Management")
        title.setStyleSheet("color:#fff;font-size:15px;font-weight:700;")
        hl.addWidget(title)
        hl.addStretch()

        add_btn = QPushButton("+ Add User")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;"
            "border-radius:5px;font-size:13px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#1b5e20;}"
        )
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_user)
        hl.addWidget(add_btn)

        root.addWidget(hdr)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "Full Name", "Username", "Role", "Branch / Warehouse", "Active", "Actions"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)

        th = self._table.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.Stretch)
        th.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(3, QHeaderView.Stretch)
        th.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(5, QHeaderView.Fixed)
        self._table.setColumnWidth(5, 160)
        th.setStyleSheet(
            "QHeaderView::section{background:#1a3a5c;color:#fff;font-weight:700;"
            "border:none;padding:4px;}"
        )
        root.addWidget(self._table, 1)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _get_session(self):
        from database.engine import get_session, init_db
        init_db()
        return get_session()

    def _fetch_warehouses(self) -> list[tuple[str, str]]:
        """Returns [(id, name), ...]"""
        from database.models.items import Warehouse
        session = self._get_session()
        try:
            rows = session.query(Warehouse).order_by(Warehouse.name).all()
            return [(w.id, w.name) for w in rows]
        finally:
            session.close()

    def _load_users(self):
        from database.models.users import User
        from database.models.items import Warehouse
        session = self._get_session()
        try:
            users = session.query(User).order_by(User.full_name).all()
            wh_map = {w.id: w.name for w in session.query(Warehouse).all()}

            self._table.setRowCount(0)
            self._user_ids: list[str] = []

            for u in users:
                r = self._table.rowCount()
                self._table.insertRow(r)
                self._user_ids.append(u.id)

                self._table.setItem(r, 0, QTableWidgetItem(u.full_name))
                self._table.setItem(r, 1, QTableWidgetItem(u.username))

                role_item = QTableWidgetItem(u.role.capitalize())
                if u.role == "admin":
                    role_item.setForeground(QColor("#1a3a5c"))
                    role_item.setFont(QFont("", -1, QFont.Bold))
                self._table.setItem(r, 2, role_item)

                branch = wh_map.get(u.warehouse_id or "", "—")
                self._table.setItem(r, 3, QTableWidgetItem(branch))

                active_item = QTableWidgetItem("Yes" if u.is_active else "No")
                active_item.setForeground(
                    QColor("#2e7d32") if u.is_active else QColor("#c62828")
                )
                self._table.setItem(r, 4, active_item)

                # Action buttons in a widget
                cell = QWidget()
                cl = QHBoxLayout(cell)
                cl.setContentsMargins(4, 2, 4, 2)
                cl.setSpacing(6)

                edit_btn = QPushButton("Edit")
                edit_btn.setFixedHeight(26)
                edit_btn.setStyleSheet(
                    "QPushButton{background:#1a6cb5;color:#fff;border:none;"
                    "border-radius:4px;font-size:12px;padding:0 8px;}"
                    "QPushButton:hover{background:#1a3a5c;}"
                )
                edit_btn.clicked.connect(
                    lambda _=False, uid=u.id: self._edit_user(uid)
                )
                cl.addWidget(edit_btn)

                toggle_lbl = "Deactivate" if u.is_active else "Activate"
                toggle_btn = QPushButton(toggle_lbl)
                toggle_btn.setFixedHeight(26)
                toggle_btn.setStyleSheet(
                    "QPushButton{background:#e65100;color:#fff;border:none;"
                    "border-radius:4px;font-size:12px;padding:0 8px;}"
                    "QPushButton:hover{background:#bf360c;}"
                ) if u.is_active else toggle_btn.setStyleSheet(
                    "QPushButton{background:#2e7d32;color:#fff;border:none;"
                    "border-radius:4px;font-size:12px;padding:0 8px;}"
                    "QPushButton:hover{background:#1b5e20;}"
                )
                toggle_btn.clicked.connect(
                    lambda _=False, uid=u.id, active=u.is_active: self._toggle_active(uid, active)
                )
                cl.addWidget(toggle_btn)
                self._table.setCellWidget(r, 5, cell)
        finally:
            session.close()

    # ── Dialogs ───────────────────────────────────────────────────────────────

    def _add_user(self):
        warehouses = self._fetch_warehouses()
        dlg = _UserDialog(warehouses=warehouses, parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            ok, err = self._save_new_user(data)
            if ok:
                self._load_users()
            else:
                QMessageBox.critical(self, "Error", f"Could not save user:\n{err}")

    def _edit_user(self, user_id: str):
        warehouses = self._fetch_warehouses()
        from database.models.users import User
        session = self._get_session()
        try:
            user = session.get(User, user_id)
            if not user:
                return
            existing = {
                "full_name":    user.full_name,
                "username":     user.username,
                "role":         user.role,
                "warehouse_id": user.warehouse_id or "",
                "is_active":    user.is_active,
            }
        finally:
            session.close()

        dlg = _UserDialog(warehouses=warehouses, existing=existing, parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            ok, err = self._update_user(user_id, data)
            if ok:
                self._load_users()
            else:
                QMessageBox.critical(self, "Error", f"Could not update user:\n{err}")

    def _toggle_active(self, user_id: str, currently_active: bool):
        action = "deactivate" if currently_active else "activate"
        reply = QMessageBox.question(
            self, "Confirm",
            f"Are you sure you want to {action} this user?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from database.models.users import User
        session = self._get_session()
        try:
            user = session.get(User, user_id)
            if user:
                user.is_active = not currently_active
                session.commit()
                try:
                    from sync.service import push_user, is_configured
                    if is_configured():
                        push_user(user_id)
                except Exception:
                    pass
        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            session.close()
        self._load_users()

    # ── DB writes ─────────────────────────────────────────────────────────────

    def _save_new_user(self, data: dict) -> tuple[bool, str]:
        from database.models.users import User
        from database.models.base import new_uuid
        session = self._get_session()
        try:
            # Check username unique
            existing = session.query(User).filter_by(username=data["username"]).first()
            if existing:
                return False, f"Username '{data['username']}' is already taken."
            pw_hash = bcrypt.hashpw(
                data["password"].encode(), bcrypt.gensalt()
            ).decode()
            user = User(
                id=new_uuid(),
                username=data["username"],
                password_hash=pw_hash,
                full_name=data["full_name"],
                role=data["role"],
                warehouse_id=data["warehouse_id"] or None,
                is_active=data["is_active"],
            )
            session.add(user)
            session.commit()
            try:
                from sync.service import push_user, is_configured
                if is_configured():
                    push_user(user.id)
            except Exception:
                pass
            return True, ""
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()

    def _update_user(self, user_id: str, data: dict) -> tuple[bool, str]:
        from database.models.users import User
        session = self._get_session()
        try:
            user = session.get(User, user_id)
            if not user:
                return False, "User not found."
            # Username uniqueness check (skip self)
            clash = session.query(User).filter(
                User.username == data["username"],
                User.id != user_id,
            ).first()
            if clash:
                return False, f"Username '{data['username']}' is already taken."

            user.full_name    = data["full_name"]
            user.username     = data["username"]
            user.role         = data["role"]
            user.warehouse_id = data["warehouse_id"] or None
            user.is_active    = data["is_active"]
            if data.get("password"):
                user.password_hash = bcrypt.hashpw(
                    data["password"].encode(), bcrypt.gensalt()
                ).decode()
            session.commit()
            try:
                from sync.service import push_user, is_configured
                if is_configured():
                    push_user(user_id)
            except Exception:
                pass
            return True, ""
        except Exception as e:
            session.rollback()
            return False, str(e)
        finally:
            session.close()


# ── Add / Edit dialog ─────────────────────────────────────────────────────────

class _UserDialog(QDialog):
    def __init__(self, warehouses: list[tuple[str, str]],
                 existing: dict | None = None, parent=None):
        super().__init__(parent)
        self._warehouses = warehouses
        self._existing   = existing
        self.setWindowTitle("Edit User" if existing else "Add User")
        self.setFixedWidth(400)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title = QLabel("Edit User" if self._existing else "Add New User")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#1a3a5c;")
        lay.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self._full_name = QLineEdit()
        self._full_name.setFixedHeight(34)
        form.addRow("Full Name:", self._full_name)

        self._username = QLineEdit()
        self._username.setFixedHeight(34)
        form.addRow("Username:", self._username)

        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setFixedHeight(34)
        pw_hint = "(leave blank to keep current)" if self._existing else ""
        self._password.setPlaceholderText(pw_hint or "Password")
        form.addRow("Password:", self._password)

        self._role = QComboBox()
        self._role.addItems(["cashier", "manager", "admin"])
        self._role.setFixedHeight(34)
        form.addRow("Role:", self._role)

        self._warehouse = QComboBox()
        self._warehouse.setFixedHeight(34)
        self._warehouse.addItem("— No branch assigned —", "")
        for wid, wname in self._warehouses:
            self._warehouse.addItem(wname, wid)
        form.addRow("Branch:", self._warehouse)

        self._active = QCheckBox("Account is active")
        self._active.setChecked(True)
        form.addRow("", self._active)

        lay.addLayout(form)

        # Pre-fill if editing
        if self._existing:
            self._full_name.setText(self._existing.get("full_name", ""))
            self._username.setText(self._existing.get("username", ""))
            idx = self._role.findText(self._existing.get("role", "cashier"))
            if idx >= 0:
                self._role.setCurrentIndex(idx)
            wid = self._existing.get("warehouse_id", "")
            for i in range(self._warehouse.count()):
                if self._warehouse.itemData(i) == wid:
                    self._warehouse.setCurrentIndex(i)
                    break
            self._active.setChecked(self._existing.get("is_active", True))

        self._err = QLabel("")
        self._err.setStyleSheet("color:#c62828;font-size:12px;")
        self._err.hide()
        lay.addWidget(self._err)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(34)
        cancel.setStyleSheet(
            "QPushButton{background:#eceff1;color:#37474f;border:none;border-radius:5px;}"
        )
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        save = QPushButton("Save")
        save.setFixedHeight(34)
        save.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;border:none;"
            "border-radius:5px;font-weight:700;}"
            "QPushButton:hover{background:#1a6cb5;}"
        )
        save.clicked.connect(self._validate)
        btn_row.addWidget(save)
        lay.addLayout(btn_row)

    def _validate(self):
        fn = self._full_name.text().strip()
        un = self._username.text().strip()
        pw = self._password.text()

        if not fn:
            self._show_err("Full name is required.")
            return
        if not un:
            self._show_err("Username is required.")
            return
        if not self._existing and not pw:
            self._show_err("Password is required for new users.")
            return
        self._err.hide()
        self.accept()

    def _show_err(self, msg: str):
        self._err.setText(msg)
        self._err.show()

    def get_data(self) -> dict:
        return {
            "full_name":    self._full_name.text().strip(),
            "username":     self._username.text().strip(),
            "password":     self._password.text(),
            "role":         self._role.currentText(),
            "warehouse_id": self._warehouse.currentData() or "",
            "is_active":    self._active.isChecked(),
        }
