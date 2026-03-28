"""
Categories & Sub-Categories management screen.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QComboBox,
    QPushButton, QLabel, QGroupBox, QFormLayout,
    QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt, Signal
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

        form.addRow("Name *", self._name_edit)
        form.addRow("Parent (Sub only)", self._parent_combo)
        form.addRow("", self._show_daily_chk)

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
        btn_row.addWidget(save_btn)
        btn_row.addWidget(clear_btn)
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
        # roots first, then children
        roots = {cid: (cname, sid) for cid, cname, pid, sid in cats if not pid}
        children = [(cid, cname, pid, sid) for cid, cname, pid, sid in cats if pid]

        # Populate parent combo
        self._parent_combo.clear()
        self._parent_combo.addItem("— None (top level) —", "")
        for cid, (cname, _) in sorted(roots.items(), key=lambda x: x[1][0]):
            self._parent_combo.addItem(cname, cid)

        # Tree
        node_map = {}
        for cid, (cname, sid) in sorted(roots.items(), key=lambda x: x[1][0]):
            label = f"★ {cname}" if sid else cname
            item  = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, (cid, sid))
            self._tree.addTopLevelItem(item)
            node_map[cid] = item

        for cid, cname, pid, sid in sorted(children, key=lambda x: x[1]):
            parent_node = node_map.get(pid)
            label = f"★ {cname}" if sid else cname
            item  = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, (cid, sid))
            if parent_node:
                parent_node.addChild(item)
            else:
                self._tree.addTopLevelItem(item)

        self._tree.expandAll()

    def _on_select(self, item: QTreeWidgetItem, _col):
        cid, sid = item.data(0, Qt.UserRole)
        self._selected_id = cid
        # Strip the ★ prefix if present
        raw_name = item.text(0).lstrip("★ ")
        self._name_edit.setText(raw_name)
        self._show_daily_chk.setChecked(bool(sid))
        # Find parent
        parent = item.parent()
        if parent:
            pid, _ = parent.data(0, Qt.UserRole)
            for i in range(self._parent_combo.count()):
                if self._parent_combo.itemData(i) == pid:
                    self._parent_combo.setCurrentIndex(i)
                    break
        else:
            self._parent_combo.setCurrentIndex(0)

    def _new_category(self):
        self._selected_id = ""
        self._name_edit.clear()
        self._parent_combo.setCurrentIndex(0)
        self._show_daily_chk.setChecked(False)
        self._status_lbl.setText("")
        self._name_edit.setFocus()

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
        )
        if ok:
            self._status_lbl.setStyleSheet("color: #2e7d32;")
            self._status_lbl.setText("✔  Saved.")
            self._load_tree()
            self._selected_id = ""
        else:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText(f"Error: {err}")
