"""
App Manager — control panel for the mobile shopping app.

Tabs:
  • Banners    — CRUD for app_banners table (image upload, sort order, links)
  • Featured   — toggle is_featured flag on items (shown in app home screen)
"""
from __future__ import annotations

import mimetypes
import os
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QMessageBox,
    QFileDialog, QFormLayout, QDialog, QDialogButtonBox,
    QAbstractItemView, QFrame, QSizePolicy,
)


class AppManagerScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_banners()
        self._load_featured()
        self._load_categories()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        hdr = QFrame()
        hdr.setStyleSheet("background:#1a3a5c; padding:6px 12px;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedSize(70, 28)
        back_btn.clicked.connect(self.back)
        title = QLabel("📱  Mobile App Manager")
        title.setStyleSheet("color:#ffffff; font-size:16px; font-weight:700;")
        hdr_lay.addWidget(back_btn)
        hdr_lay.addSpacing(12)
        hdr_lay.addWidget(title)
        hdr_lay.addStretch()
        root.addWidget(hdr)

        tabs = QTabWidget()
        tabs.setStyleSheet("QTabWidget::pane { border:none; }")
        tabs.addTab(self._build_banners_tab(), "🖼  Banners")
        tabs.addTab(self._build_featured_tab(), "⭐  Featured Items")
        tabs.addTab(self._build_categories_tab(), "🗂  Categories")
        root.addWidget(tabs)

    # ── Banners tab ───────────────────────────────────────────────────────────

    def _build_banners_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        toolbar = QHBoxLayout()
        add_btn = QPushButton("＋  Add Banner")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._add_banner)
        edit_btn = QPushButton("✎  Edit")
        edit_btn.setObjectName("secondaryBtn")
        edit_btn.setFixedHeight(32)
        edit_btn.clicked.connect(self._edit_banner)
        del_btn = QPushButton("✖  Delete")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedHeight(32)
        del_btn.clicked.connect(self._delete_banner)
        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._load_banners)
        toggle_btn = QPushButton("⏺  Toggle Active")
        toggle_btn.setObjectName("secondaryBtn")
        toggle_btn.setFixedHeight(32)
        toggle_btn.clicked.connect(self._toggle_banner_active)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(edit_btn)
        toolbar.addWidget(toggle_btn)
        toolbar.addWidget(del_btn)
        toolbar.addStretch()
        toolbar.addWidget(refresh_btn)
        lay.addLayout(toolbar)

        self._banner_tbl = QTableWidget()
        self._banner_tbl.setColumnCount(6)
        self._banner_tbl.setHorizontalHeaderLabels(
            ["ID", "Title", "Sort", "Active", "Link Type", "Link Value"]
        )
        self._banner_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._banner_tbl.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._banner_tbl.setColumnWidth(0, 80)
        self._banner_tbl.setColumnWidth(2, 50)
        self._banner_tbl.setColumnWidth(3, 60)
        self._banner_tbl.setColumnWidth(4, 90)
        self._banner_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._banner_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._banner_tbl.setAlternatingRowColors(True)
        self._banner_tbl.verticalHeader().setVisible(False)
        self._banner_tbl.doubleClicked.connect(self._edit_banner)
        lay.addWidget(self._banner_tbl)

        self._banner_status = QLabel("")
        self._banner_status.setStyleSheet("font-size:11px; color:#2e7d32;")
        lay.addWidget(self._banner_status)
        return w

    def _load_banners(self):
        from sync.service import is_configured, fetch_banners_remote
        self._banner_tbl.setRowCount(0)
        if not is_configured():
            self._banner_status.setStyleSheet("color:#c62828;")
            self._banner_status.setText("Supabase not configured.")
            return
        banners, err = fetch_banners_remote()
        if err:
            self._banner_status.setStyleSheet("color:#c62828;")
            self._banner_status.setText(f"Error: {err}")
            return
        self._banners_data = banners
        for b in banners:
            row = self._banner_tbl.rowCount()
            self._banner_tbl.insertRow(row)
            self._banner_tbl.setItem(row, 0, QTableWidgetItem(str(b.get("id", ""))[:8]))
            self._banner_tbl.item(row, 0).setData(Qt.UserRole, b.get("id", ""))
            self._banner_tbl.setItem(row, 1, QTableWidgetItem(b.get("title", "")))
            self._banner_tbl.setItem(row, 2, QTableWidgetItem(str(b.get("sort_order", 0))))
            active_item = QTableWidgetItem("Yes" if b.get("is_active") else "No")
            active_item.setForeground(QColor("#2e7d32") if b.get("is_active") else QColor("#c62828"))
            self._banner_tbl.setItem(row, 3, active_item)
            self._banner_tbl.setItem(row, 4, QTableWidgetItem(b.get("link_type", "none")))
            self._banner_tbl.setItem(row, 5, QTableWidgetItem(b.get("link_value", "") or ""))
        self._banner_status.setStyleSheet("color:#2e7d32;")
        self._banner_status.setText(f"{len(banners)} banner(s) loaded.")

    def _selected_banner(self) -> dict | None:
        row = self._banner_tbl.currentRow()
        if row < 0:
            return None
        banner_id = self._banner_tbl.item(row, 0).data(Qt.UserRole)
        for b in getattr(self, "_banners_data", []):
            if b.get("id") == banner_id:
                return b
        return None

    def _add_banner(self):
        dlg = BannerDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            from sync.service import upsert_banner
            ok, err = upsert_banner(data)
            if ok:
                self._load_banners()
            else:
                QMessageBox.warning(self, "Error", err)

    def _edit_banner(self):
        banner = self._selected_banner()
        if not banner:
            QMessageBox.information(self, "Select row", "Select a banner first.")
            return
        dlg = BannerDialog(banner=banner, parent=self)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            from sync.service import upsert_banner
            ok, err = upsert_banner(data)
            if ok:
                self._load_banners()
            else:
                QMessageBox.warning(self, "Error", err)

    def _toggle_banner_active(self):
        banner = self._selected_banner()
        if not banner:
            QMessageBox.information(self, "Select row", "Select a banner first.")
            return
        new_state = not banner.get("is_active", True)
        from sync.service import upsert_banner
        ok, err = upsert_banner({**banner, "is_active": new_state})
        if ok:
            self._load_banners()
        else:
            QMessageBox.warning(self, "Error", err)

    def _delete_banner(self):
        banner = self._selected_banner()
        if not banner:
            QMessageBox.information(self, "Select row", "Select a banner first.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete banner '{banner.get('title', '')}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from sync.service import delete_banner
        ok, err = delete_banner(banner["id"])
        if ok:
            self._load_banners()
        else:
            QMessageBox.warning(self, "Error", err)

    # ── Featured Items tab ────────────────────────────────────────────────────

    def _build_featured_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        toolbar = QHBoxLayout()
        self._feat_search = QLineEdit()
        self._feat_search.setPlaceholderText("Search items…")
        self._feat_search.setFixedHeight(30)
        self._feat_search.textChanged.connect(self._filter_featured)
        push_btn = QPushButton("☁  Push changes to app")
        push_btn.setObjectName("primaryBtn")
        push_btn.setFixedHeight(32)
        push_btn.clicked.connect(self._push_featured)
        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._load_featured)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self._feat_search, 1)
        toolbar.addStretch()
        toolbar.addWidget(push_btn)
        toolbar.addWidget(refresh_btn)
        lay.addLayout(toolbar)

        info = QLabel("Check items to mark as Featured — they appear in the ⭐ Featured section of the app home screen.")
        info.setStyleSheet("font-size:11px; color:#666;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._feat_tbl = QTableWidget()
        self._feat_tbl.setColumnCount(4)
        self._feat_tbl.setHorizontalHeaderLabels(["Featured", "Code", "Name", "Category"])
        self._feat_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._feat_tbl.setColumnWidth(0, 70)
        self._feat_tbl.setColumnWidth(1, 110)
        self._feat_tbl.setColumnWidth(3, 140)
        self._feat_tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._feat_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._feat_tbl.setAlternatingRowColors(True)
        self._feat_tbl.verticalHeader().setVisible(False)
        lay.addWidget(self._feat_tbl)

        self._feat_status = QLabel("")
        self._feat_status.setStyleSheet("font-size:11px; color:#2e7d32;")
        lay.addWidget(self._feat_status)
        return w

    def _load_featured(self):
        from services.item_service import ItemService
        self._feat_tbl.setRowCount(0)
        items = ItemService.search_items(active_only=False, limit=99999)
        self._all_items = items
        self._populate_featured_table(items)

    def _populate_featured_table(self, items):
        self._feat_tbl.setRowCount(0)
        for item in items:
            row = self._feat_tbl.rowCount()
            self._feat_tbl.insertRow(row)

            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if item.is_featured else Qt.Unchecked)
            chk.setData(Qt.UserRole, item.id)
            self._feat_tbl.setItem(row, 0, chk)
            self._feat_tbl.setItem(row, 1, QTableWidgetItem(item.code))
            self._feat_tbl.setItem(row, 2, QTableWidgetItem(item.name))
            self._feat_tbl.setItem(row, 3, QTableWidgetItem(item.category))
        self._feat_status.setStyleSheet("color:#2e7d32;")
        self._feat_status.setText(f"{len(items)} item(s) shown.")

    def _filter_featured(self, text: str):
        text = text.lower()
        filtered = [i for i in getattr(self, "_all_items", [])
                    if text in i.name.lower() or text in i.code.lower() or text in i.category.lower()]
        self._populate_featured_table(filtered)

    def _push_featured(self):
        from services.item_service import ItemService
        from sync.service import is_configured, push_item
        if not is_configured():
            QMessageBox.warning(self, "Not configured", "Supabase sync is not configured.")
            return

        changed = 0
        errors  = []
        for row in range(self._feat_tbl.rowCount()):
            chk = self._feat_tbl.item(row, 0)
            if not chk:
                continue
            item_id  = chk.data(Qt.UserRole)
            featured = chk.checkState() == Qt.Checked
            current  = next((i for i in getattr(self, "_all_items", []) if i.id == item_id), None)
            if current and bool(current.is_featured) != featured:
                ItemService.set_featured(item_id, featured)
                ok, err = push_item(item_id)
                if ok:
                    changed += 1
                else:
                    errors.append(err)

        if errors:
            self._feat_status.setStyleSheet("color:#c62828;")
            self._feat_status.setText(f"{changed} pushed, {len(errors)} error(s): {errors[0]}")
        else:
            self._feat_status.setStyleSheet("color:#2e7d32;")
            self._feat_status.setText(f"✔ {changed} item(s) pushed to app.")
        self._load_featured()


    # ── Categories tab ────────────────────────────────────────────────────────

    def _build_categories_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        toolbar = QHBoxLayout()
        push_btn = QPushButton("☁  Push all category images to app")
        push_btn.setObjectName("primaryBtn")
        push_btn.setFixedHeight(32)
        push_btn.clicked.connect(self._push_category_images)
        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._load_categories)
        toolbar.addWidget(push_btn)
        toolbar.addStretch()
        toolbar.addWidget(refresh_btn)
        lay.addLayout(toolbar)

        info = QLabel("Categories with an image URL (set in Stock → Categories) will show photos in the app.")
        info.setStyleSheet("font-size:11px; color:#666;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._cat_tbl = QTableWidget()
        self._cat_tbl.setColumnCount(2)
        self._cat_tbl.setHorizontalHeaderLabels(["Category", "Image URL"])
        self._cat_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._cat_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._cat_tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cat_tbl.setAlternatingRowColors(True)
        self._cat_tbl.verticalHeader().setVisible(False)
        lay.addWidget(self._cat_tbl)

        self._cat_status = QLabel("")
        self._cat_status.setStyleSheet("font-size:11px;")
        lay.addWidget(self._cat_status)
        return w

    def _load_categories(self):
        from services.item_service import ItemService
        self._cat_tbl.setRowCount(0)
        cats = ItemService.get_categories()
        has_img = 0
        for cid, name, pid, sid, sot, photo_url, soh, ia in cats:
            row = self._cat_tbl.rowCount()
            self._cat_tbl.insertRow(row)
            self._cat_tbl.setItem(row, 0, QTableWidgetItem(name))
            url_item = QTableWidgetItem(photo_url or "")
            if photo_url:
                url_item.setForeground(QColor("#2e7d32"))
                has_img += 1
            else:
                url_item.setForeground(QColor("#aaa"))
            self._cat_tbl.setItem(row, 1, url_item)
        self._cat_status.setStyleSheet("color:#555;")
        self._cat_status.setText(f"{self._cat_tbl.rowCount()} categories — {has_img} with image.")

    def _push_category_images(self):
        from sync.service import is_configured, push_categories
        if not is_configured():
            QMessageBox.warning(self, "Not configured", "Supabase sync is not configured.")
            return
        ok, err = push_categories()
        if ok:
            self._cat_status.setStyleSheet("color:#2e7d32;")
            self._cat_status.setText("✔ Category images pushed to app.")
        else:
            self._cat_status.setStyleSheet("color:#c62828;")
            self._cat_status.setText(f"Error: {err}")


# ── Banner add/edit dialog ────────────────────────────────────────────────────

class BannerDialog(QDialog):
    def __init__(self, banner: dict | None = None, parent=None):
        super().__init__(parent)
        self._banner = banner or {}
        self._uploaded_url = banner.get("image_url", "") if banner else ""
        self.setWindowTitle("Add Banner" if not banner else "Edit Banner")
        self.setMinimumWidth(420)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self._title_edit = QLineEdit(self._banner.get("title", ""))
        form.addRow("Title:", self._title_edit)

        self._subtitle_edit = QLineEdit(self._banner.get("subtitle", "") or "")
        self._subtitle_edit.setPlaceholderText("Small text shown below the title…")
        form.addRow("Subtitle:", self._subtitle_edit)

        self._sort_spin = QSpinBox()
        self._sort_spin.setRange(0, 999)
        self._sort_spin.setValue(self._banner.get("sort_order", 0))
        form.addRow("Sort order:", self._sort_spin)

        self._active_chk = QCheckBox("Active")
        self._active_chk.setChecked(self._banner.get("is_active", True))
        form.addRow("", self._active_chk)

        self._link_type = QComboBox()
        self._link_type.addItems(["none", "category", "item"])
        idx = self._link_type.findText(self._banner.get("link_type", "none"))
        if idx >= 0:
            self._link_type.setCurrentIndex(idx)
        form.addRow("Link type:", self._link_type)

        self._link_value = QLineEdit(self._banner.get("link_value", "") or "")
        self._link_value.setPlaceholderText("Category name or item UUID")
        form.addRow("Link value:", self._link_value)

        # Image row — URL input or file upload
        img_row = QHBoxLayout()
        self._img_url_edit = QLineEdit(self._uploaded_url or "")
        self._img_url_edit.setPlaceholderText("Paste image URL or upload a file…")
        self._img_url_edit.textChanged.connect(lambda t: setattr(self, '_uploaded_url', t.strip()))
        upload_btn = QPushButton("Upload file…")
        upload_btn.setObjectName("secondaryBtn")
        upload_btn.setFixedHeight(26)
        upload_btn.clicked.connect(self._upload_image)
        img_row.addWidget(self._img_url_edit, 1)
        img_row.addWidget(upload_btn)
        form.addRow("Image URL:", img_row)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _upload_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Banner Image", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        from sync.service import is_configured, upload_to_storage
        if not is_configured():
            QMessageBox.warning(self, "Not configured", "Supabase sync is not configured.")
            return
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        ext  = os.path.splitext(path)[1].lower()
        remote_path = f"banners/{uuid.uuid4().hex}{ext}"
        with open(path, "rb") as f:
            data = f.read()
        ok, result = upload_to_storage("product-images", remote_path, data, mime)
        if ok:
            self._uploaded_url = result
            self._img_url_edit.setText(result)
        else:
            QMessageBox.warning(self, "Upload failed", result)

    def get_data(self) -> dict:
        data = {
            "title":       self._title_edit.text().strip(),
            "subtitle":    self._subtitle_edit.text().strip() or None,
            "sort_order":  self._sort_spin.value(),
            "is_active":   self._active_chk.isChecked(),
            "link_type":   self._link_type.currentText(),
            "link_value":  self._link_value.text().strip() or None,
            "image_url":   self._uploaded_url or None,
        }
        if self._banner.get("id"):
            data["id"] = self._banner["id"]
        return data
