"""Brands management screen."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLineEdit,
    QPushButton, QLabel, QGroupBox, QFormLayout,
)
from PySide6.QtCore import Qt, Signal
from services.item_service import ItemService


class BrandsScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_id = ""
        self._build_ui()
        self._load()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        back_btn = QPushButton("← Back"); back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedHeight(32); back_btn.clicked.connect(self.back.emit)
        top.addWidget(back_btn)
        title = QLabel("Brands"); title.setObjectName("sectionTitle")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # List
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0,0,8,0)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        ll.addWidget(self._list)
        new_btn = QPushButton("+ New Brand"); new_btn.setObjectName("primaryBtn")
        new_btn.setFixedHeight(32); new_btn.clicked.connect(self._new)
        ll.addWidget(new_btn)
        splitter.addWidget(left)

        # Form
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(8,0,0,0)
        grp = QGroupBox("Brand Details"); form = QFormLayout(grp); form.setSpacing(8)
        self._name_edit = QLineEdit(); self._name_edit.setPlaceholderText("Brand name")
        form.addRow("Name *", self._name_edit)
        rl.addWidget(grp)

        self._status_lbl = QLabel(""); self._status_lbl.setObjectName("errorLabel")
        rl.addWidget(self._status_lbl)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾  Save"); save_btn.setObjectName("successBtn")
        save_btn.setFixedHeight(32); save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn); btn_row.addStretch()
        rl.addLayout(btn_row); rl.addStretch()
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2); splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

    def _load(self):
        self._list.clear()
        for bid, bname in ItemService.get_brands():
            item = QListWidgetItem(bname)
            item.setData(Qt.UserRole, bid)
            self._list.addItem(item)

    def _on_select(self, item: QListWidgetItem):
        self._selected_id = item.data(Qt.UserRole)
        self._name_edit.setText(item.text())

    def _new(self):
        self._selected_id = ""
        self._name_edit.clear(); self._name_edit.setFocus()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText("Name is required."); return
        ok, err = ItemService.save_brand(self._selected_id, name)
        if ok:
            self._status_lbl.setStyleSheet("color: #2e7d32;")
            self._status_lbl.setText("✔  Saved.")
            self._load(); self._selected_id = ""
        else:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText(f"Error: {err}")
