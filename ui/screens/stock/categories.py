"""
Categories & Sub-Categories management screen.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QComboBox,
    QPushButton, QLabel, QGroupBox, QFormLayout,
    QMessageBox, QCheckBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from services.item_service import ItemService
from database.models.base import new_uuid


class CategoriesScreen(QWidget):
    back = Signal()

    def __init__(self, subcategories_mode: bool = False, parent=None):
        """
        subcategories_mode=True  → shows the Sub Categories view (parent filter enabled)
        subcategories_mode=False → shows full Categories tree
        """
        super().__init__(parent)
        self._mode = subcategories_mode
        self._selected_id = ""
        self._photo_url   = ""
        self._build_ui()
        self._load_tree()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        title = QLabel("Sub Categories" if self._mode else "Categories")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: tree ───────────────────────────────────────────────────────
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Categories")
        self._tree.setColumnCount(1)
        self._tree.itemClicked.connect(self._on_select)
        ll.addWidget(self._tree)

        new_btn = QPushButton("+ New Category")
        new_btn.setObjectName("primaryBtn")
        new_btn.setFixedHeight(32)
        new_btn.clicked.connect(self._new_category)
        ll.addWidget(new_btn)
        splitter.addWidget(left)

        # ── Right: edit form ─────────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)

        grp = QGroupBox("Category Details")
        form = QFormLayout(grp)
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Category name")

        self._parent_combo = QComboBox()
        self._parent_combo.setMinimumWidth(200)

        self._show_daily_chk = QCheckBox("Show total in Daily Sales summary")
        self._show_daily_chk.setStyleSheet("font-size:12px;color:#1a3a5c;font-weight:600;")

        self._show_touch_chk = QCheckBox("Show on Touch Screen (POS touch mode)")
        self._show_touch_chk.setStyleSheet("font-size:12px;color:#00695c;font-weight:600;")

        self._show_home_chk = QCheckBox("Show on App Home Screen")
        self._show_home_chk.setStyleSheet("font-size:12px;color:#1a6cb5;font-weight:600;")

        # Photo URL
        self._photo_url_edit = QLineEdit()
        self._photo_url_edit.setPlaceholderText("Paste image URL or upload…")
        self._photo_url_edit.editingFinished.connect(self._refresh_preview)
        url_row = QHBoxLayout()
        url_row.addWidget(self._photo_url_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setObjectName("secondaryBtn")
        browse_btn.setFixedHeight(24)
        browse_btn.clicked.connect(self._browse_photo)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.setFixedHeight(24)
        clear_btn.clicked.connect(self._clear_photo)
        url_row.addWidget(browse_btn)
        url_row.addWidget(clear_btn)

        self._img_preview = QLabel()
        self._img_preview.setFixedHeight(72)
        self._img_preview.setAlignment(Qt.AlignCenter)
        self._img_preview.setStyleSheet(
            "background:#f8f8f8; border:1px solid #c0ccd8; border-radius:3px; color:#aaa;"
        )
        self._img_preview.setText("[ No Image ]")

        form.addRow("Name *", self._name_edit)
        form.addRow("Parent (Sub only)", self._parent_combo)
        form.addRow("", self._show_daily_chk)
        form.addRow("", self._show_touch_chk)
        form.addRow("", self._show_home_chk)
        form.addRow("App Image:", url_row)
        form.addRow("", self._img_preview)

        rl.addWidget(grp)

        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("errorLabel")
        rl.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾  Save")
        save_btn.setObjectName("successBtn")
        save_btn.setFixedHeight(32)
        save_btn.clicked.connect(self._save)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("secondaryBtn")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._clear)
        del_btn = QPushButton("✖  Delete")
        del_btn.setObjectName("dangerBtn")
        del_btn.setFixedHeight(32)
        del_btn.clicked.connect(self._delete_category)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        rl.addLayout(btn_row)
        rl.addStretch()

        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedHeight(32)
        back_btn.clicked.connect(self.back.emit)
        rl.addWidget(back_btn)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _load_tree(self):
        self._tree.clear()
        cats = ItemService.get_categories()
        # tuple: (id, name, parent_id, show_in_daily, show_on_touch, photo_url, show_on_home)
        roots    = {cid: (cname, sid, sot, pu, soh) for cid, cname, pid, sid, sot, pu, soh in cats if not pid}
        children = [(cid, cname, pid, sid, sot, pu, soh) for cid, cname, pid, sid, sot, pu, soh in cats if pid]

        self._parent_combo.clear()
        self._parent_combo.addItem("— None (top level) —", "")
        for cid, (cname, _, _sot, _pu, _soh) in sorted(roots.items(), key=lambda x: x[1][0]):
            self._parent_combo.addItem(cname, cid)

        node_map = {}
        for cid, (cname, sid, sot, pu, soh) in sorted(roots.items(), key=lambda x: x[1][0]):
            label = f"★ {cname}" if sid else cname
            item  = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, (cid, sid, sot, pu, soh))
            self._tree.addTopLevelItem(item)
            node_map[cid] = item

        for cid, cname, pid, sid, sot, pu, soh in sorted(children, key=lambda x: x[1]):
            parent_node = node_map.get(pid)
            label = f"★ {cname}" if sid else cname
            item  = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, (cid, sid, sot, pu, soh))
            if parent_node:
                parent_node.addChild(item)
            else:
                self._tree.addTopLevelItem(item)

        self._tree.expandAll()

    def _on_select(self, item: QTreeWidgetItem, _col):
        cid, sid, sot, pu, soh = item.data(0, Qt.UserRole)
        self._selected_id = cid
        raw_name = item.text(0).lstrip("★ ")
        self._name_edit.setText(raw_name)
        self._show_daily_chk.setChecked(bool(sid))
        self._show_touch_chk.setChecked(bool(sot))
        self._show_home_chk.setChecked(bool(soh))
        self._photo_url = pu or ""
        self._photo_url_edit.setText(self._photo_url)
        self._refresh_preview()
        parent = item.parent()
        if parent:
            pid, _, _sot, _pu = parent.data(0, Qt.UserRole)
            for i in range(self._parent_combo.count()):
                if self._parent_combo.itemData(i) == pid:
                    self._parent_combo.setCurrentIndex(i)
                    break
        else:
            self._parent_combo.setCurrentIndex(0)

    def _new_category(self):
        self._selected_id = ""
        self._photo_url   = ""
        self._name_edit.clear()
        self._photo_url_edit.clear()
        self._refresh_preview()
        self._parent_combo.setCurrentIndex(0)
        self._show_daily_chk.setChecked(False)
        self._show_touch_chk.setChecked(False)
        self._show_home_chk.setChecked(False)
        self._status_lbl.setText("")
        self._name_edit.setFocus()

    # ── Photo helpers ─────────────────────────────────────────────────────────

    def _refresh_preview(self):
        url = self._photo_url_edit.text().strip()
        self._photo_url = url
        if url:
            self._img_preview.setText("🖼  Image set")
            self._img_preview.setStyleSheet(
                "background:#f0f7ff; border:1px solid #c0ccd8; border-radius:3px; color:#1a6cb5;"
            )
        else:
            self._img_preview.setPixmap(QPixmap())
            self._img_preview.setText("[ No Image ]")
            self._img_preview.setStyleSheet(
                "background:#f8f8f8; border:1px solid #c0ccd8; border-radius:3px; color:#aaa;"
            )

    def _delete_category(self):
        if not self._selected_id:
            return
        name = self._name_edit.text().strip()
        reply = QMessageBox.question(
            self, "Delete Category",
            f"Delete '{name}'? Items in this category will lose their category assignment.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from database.engine import get_session, init_db
        from database.models.items import Category
        init_db()
        session = get_session()
        try:
            cat = session.get(Category, self._selected_id)
            if cat:
                session.delete(cat)
                session.commit()
        except Exception as e:
            session.rollback()
            QMessageBox.warning(self, "Error", str(e))
            return
        finally:
            session.close()
        # Remove from Supabase (categories_central + app_categories)
        try:
            from sync.service import is_configured, _url, _headers
            import requests as _req
            if is_configured():
                _req.delete(
                    f"{_url('categories_central')}?id=eq.{self._selected_id}",
                    headers=_headers(),
                    timeout=10,
                )
                _req.delete(
                    f"{_url('app_categories')}?name=eq.{name}",
                    headers=_headers(),
                    timeout=10,
                )
        except Exception:
            pass

        self._new_category()
        self._load_tree()
        self._status_lbl.setStyleSheet("color:#2e7d32;")
        self._status_lbl.setText("Deleted.")

    def _browse_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Category Image", "",
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if not path:
            return
        from sync.service import is_configured, upload_to_storage
        if not is_configured():
            QMessageBox.warning(self, "Not configured", "Supabase sync is not configured.")
            return
        import mimetypes, os
        mime = mimetypes.guess_type(path)[0] or "image/jpeg"
        ext  = os.path.splitext(path)[1].lower()
        remote_path = f"categories/{self._selected_id or 'new'}{ext}"
        with open(path, "rb") as f:
            data = f.read()
        ok, result = upload_to_storage("product-images", remote_path, data, mime)
        if ok:
            self._photo_url_edit.setText(result)
            self._refresh_preview()
        else:
            QMessageBox.warning(self, "Upload failed", result)

    def _clear_photo(self):
        self._photo_url_edit.clear()
        self._refresh_preview()

    def _clear(self):
        self._new_category()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText("Name is required.")
            return
        parent_id = self._parent_combo.currentData() or ""
        ok, err = ItemService.save_category(
            self._selected_id, name, parent_id,
            show_in_daily=self._show_daily_chk.isChecked(),
            show_on_touch=self._show_touch_chk.isChecked(),
            photo_url=self._photo_url_edit.text().strip(),
            show_on_home=self._show_home_chk.isChecked(),
        )
        if ok:
            if err:
                self._status_lbl.setStyleSheet("color: #e65100;")
                self._status_lbl.setText(f"✔ Saved locally — sync warning: {err}")
            else:
                self._status_lbl.setStyleSheet("color: #2e7d32;")
                self._status_lbl.setText("✔  Saved and synced.")
            self._load_tree()
            # Keep _selected_id so repeated saves UPDATE instead of creating duplicates
        else:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText(f"Error: {err}")
