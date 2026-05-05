"""Warehouse Table management screen."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QLineEdit,
    QPushButton, QLabel, QGroupBox, QFormLayout, QCheckBox, QSpinBox, QComboBox,
)
from PySide6.QtCore import Qt, Signal
from services.item_service import ItemService


class WarehouseTableScreen(QWidget):
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
        back_btn_top = QPushButton("← Back"); back_btn_top.setObjectName("secondaryBtn")
        back_btn_top.setFixedHeight(32); back_btn_top.clicked.connect(self.back.emit)
        top.addWidget(back_btn_top)
        title = QLabel("Warehouse Table"); title.setObjectName("sectionTitle")
        top.addWidget(title)
        top.addStretch()
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # List
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0,0,8,0)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_select)
        ll.addWidget(self._list)
        new_btn = QPushButton("+ New Warehouse"); new_btn.setObjectName("primaryBtn")
        new_btn.setFixedHeight(32); new_btn.clicked.connect(self._new)
        ll.addWidget(new_btn)
        splitter.addWidget(left)

        # Form
        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(8,0,0,0)
        grp = QGroupBox("Warehouse Details"); form = QFormLayout(grp); form.setSpacing(8)
        self._num_spin  = QSpinBox()
        self._num_spin.setRange(-1, 9999); self._num_spin.setSpecialValueText("—")
        self._num_spin.setValue(-1)
        self._name_edit = QLineEdit(); self._name_edit.setPlaceholderText("Warehouse name")
        self._loc_edit  = QLineEdit(); self._loc_edit.setPlaceholderText("Location / description")
        self._default_chk = QCheckBox("Set as Default Warehouse")

        self._cust_combo = QComboBox()
        self._cust_combo.setMinimumWidth(200)
        self._cust_combo.setFixedHeight(28)

        form.addRow("Number",           self._num_spin)
        form.addRow("Name *",           self._name_edit)
        form.addRow("Location",         self._loc_edit)
        form.addRow("Default Customer", self._cust_combo)
        form.addRow("",                 self._default_chk)
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
        # Refresh customer combo
        from services.customer_service import CustomerService
        self._customers = CustomerService.list_customers()
        self._cust_combo.clear()
        self._cust_combo.addItem("— None —", "")
        for c in self._customers:
            self._cust_combo.addItem(f"{c['name']}  ({c['code']})" if c['code'] else c['name'], c['id'])

        self._list.clear()
        for wid, wname, is_def, wnum, def_cust_id in ItemService.get_warehouses():
            num_str = f"[{wnum}] " if wnum is not None else ""
            label = f"{num_str}{wname}  {'★ Default' if is_def else ''}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, (wid, wname, "", is_def, wnum, def_cust_id))
            self._list.addItem(item)

    def _on_select(self, item: QListWidgetItem):
        wid, wname, loc, is_def, wnum, def_cust_id = item.data(Qt.UserRole)
        self._selected_id = wid
        self._num_spin.setValue(wnum if wnum is not None else -1)
        self._name_edit.setText(wname)
        self._loc_edit.setText(loc)
        self._default_chk.setChecked(is_def)
        idx = self._cust_combo.findData(def_cust_id or "")
        self._cust_combo.setCurrentIndex(max(0, idx))

    def _new(self):
        self._selected_id = ""
        self._num_spin.setValue(-1)
        self._name_edit.clear(); self._loc_edit.clear()
        self._default_chk.setChecked(False)
        self._cust_combo.setCurrentIndex(0)
        self._name_edit.setFocus()

    def _save(self):
        name = self._name_edit.text().strip()
        if not name:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText("Name is required."); return
        num = self._num_spin.value() if self._num_spin.value() >= 0 else None  # -1 = "—" = no number
        ok, err = ItemService.save_warehouse(
            self._selected_id, name, self._loc_edit.text().strip(),
            self._default_chk.isChecked(),
            number=num,
            default_customer_id=self._cust_combo.currentData() or None,
        )
        if ok:
            self._status_lbl.setStyleSheet("color: #2e7d32;")
            self._status_lbl.setText("✔  Saved."); self._load(); self._selected_id = ""
        else:
            self._status_lbl.setStyleSheet("color: #c62828;")
            self._status_lbl.setText(f"Error: {err}")
