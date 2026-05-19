"""
TouchOverlay — full-screen restaurant-style touch POS mode.

Layout:
  Left  (65%) — category tabs + large item tile grid (4 cols × N rows)
  Right (35%) — live order cart, +/- qty per line, grand total, PAY / Clear / Exit
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QFrame, QLabel, QPushButton, QScrollArea,
)
from PySide6.QtCore import Qt, Signal, QTimer


class TouchOverlay(QWidget):
    exit_requested     = Signal()
    invoices_requested = Signal()

    def __init__(self, pos_screen, parent=None):
        super().__init__(parent)
        self._pos = pos_screen
        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle{background:#2a4a6a;}")

        # Left — big tile panel
        from ui.screens.pos.touch_panel import TouchPanel
        self._tile_panel = TouchPanel(cols=4, tile_size=150)
        self._tile_panel.item_selected.connect(self._on_item_selected)
        self._tile_panel.exit_requested.connect(self.exit_requested)
        splitter.addWidget(self._tile_panel)

        # Right — live cart
        splitter.addWidget(self._make_cart_panel())

        splitter.setStretchFactor(0, 68)
        splitter.setStretchFactor(1, 32)
        splitter.setSizes([900, 320])
        root.addWidget(splitter)

    def _make_cart_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#1a1a2e;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Header (customer + exit button) ──────────────────────────────────
        hdr = QFrame()
        hdr.setFixedHeight(50)
        hdr.setStyleSheet("background:#1a3a5c;border-bottom:2px solid #2a5a8c;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 0, 14, 0)
        self._cust_lbl = QLabel("👤  Walk-In")
        self._cust_lbl.setStyleSheet("color:#f0c040;font-size:15px;font-weight:700;")
        hl.addWidget(self._cust_lbl)

        cust_btn = QPushButton("👥")
        cust_btn.setFixedSize(36, 34)
        cust_btn.setCursor(Qt.PointingHandCursor)
        cust_btn.setToolTip("Change Customer")
        cust_btn.setStyleSheet(
            "QPushButton{background:#5c6bc0;color:#fff;border:none;"
            "border-radius:5px;font-size:16px;}"
            "QPushButton:hover{background:#3949ab;}"
        )
        cust_btn.clicked.connect(lambda: self._pos._change_customer())
        hl.addWidget(cust_btn)

        hl.addStretch()
        inv_btn = QPushButton("🧾  Invoices")
        inv_btn.setFixedHeight(34)
        inv_btn.setCursor(Qt.PointingHandCursor)
        inv_btn.setStyleSheet(
            "QPushButton{background:#1565c0;color:#fff;border:none;"
            "border-radius:5px;font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#1976d2;}"
        )
        inv_btn.clicked.connect(self.invoices_requested)
        hl.addWidget(inv_btn)

        exit_btn = QPushButton("✕  Exit Touch")
        exit_btn.setFixedHeight(34)
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;"
            "border-radius:5px;font-size:12px;font-weight:700;padding:0 14px;}"
            "QPushButton:hover{background:#263238;}"
        )
        exit_btn.clicked.connect(self.exit_requested)
        hl.addWidget(exit_btn)
        lay.addWidget(hdr)

        # ── Last invoice strip ────────────────────────────────────────────────
        last_row = QFrame()
        last_row.setFixedHeight(24)
        last_row.setStyleSheet("background:#0d1117;border-bottom:1px solid #1a3a5c;")
        lr_lay = QHBoxLayout(last_row)
        lr_lay.setContentsMargins(14, 0, 14, 0)
        lr_lay.setSpacing(6)
        last_lbl = QLabel("Last Invoice:")
        last_lbl.setStyleSheet("color:#607d8b;font-size:10px;")
        lr_lay.addWidget(last_lbl)
        self._last_inv_lbl = QLabel("—")
        self._last_inv_lbl.setStyleSheet("color:#80cbc4;font-size:10px;font-weight:700;")
        lr_lay.addWidget(self._last_inv_lbl)
        lr_lay.addStretch()
        lay.addWidget(last_row)

        # ── Line count pill ───────────────────────────────────────────────────
        self._count_lbl = QLabel("No items")
        self._count_lbl.setAlignment(Qt.AlignCenter)
        self._count_lbl.setFixedHeight(26)
        self._count_lbl.setStyleSheet(
            "color:#607d8b;font-size:11px;"
            "background:#111827;border-bottom:1px solid #263238;"
        )
        lay.addWidget(self._count_lbl)

        # ── Scrollable cart lines ─────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            "QScrollArea{border:none;background:#1a1a2e;}"
            "QScrollBar:vertical{width:6px;background:#111827;border-radius:3px;}"
            "QScrollBar::handle:vertical{background:#2a5a8c;border-radius:3px;}"
        )
        self._lines_widget = QWidget()
        self._lines_widget.setStyleSheet("background:#1a1a2e;")
        self._lines_layout = QVBoxLayout(self._lines_widget)
        self._lines_layout.setContentsMargins(8, 8, 8, 8)
        self._lines_layout.setSpacing(6)
        self._lines_layout.addStretch()
        self._scroll.setWidget(self._lines_widget)
        self._scroll.verticalScrollBar().rangeChanged.connect(
            lambda _min, _max: self._scroll.verticalScrollBar().setValue(_max)
        )
        lay.addWidget(self._scroll, 1)

        # ── Grand total ───────────────────────────────────────────────────────
        tot_frame = QFrame()
        tot_frame.setFixedHeight(90)
        tot_frame.setStyleSheet(
            "QFrame{background:#111827;border-top:2px solid #2a5a8c;}"
            "QLabel{background:transparent;border:none;}"
        )
        tl = QVBoxLayout(tot_frame)
        tl.setContentsMargins(16, 8, 16, 8)
        tl.setSpacing(2)
        self._usd_lbl = QLabel("")
        self._usd_lbl.setAlignment(Qt.AlignRight)
        self._usd_lbl.setStyleSheet("color:#607d8b;font-size:15px;")
        tl.addWidget(self._usd_lbl)
        _cur = getattr(self._pos, "_currency", "LBP")
        self._total_lbl = QLabel(f"{'$' if _cur == 'USD' else 'ل.ل'}  0")
        self._total_lbl.setAlignment(Qt.AlignRight)
        self._total_lbl.setStyleSheet(
            "color:#00e676;font-size:30px;font-weight:700;letter-spacing:1px;"
        )
        tl.addWidget(self._total_lbl)
        lay.addWidget(tot_frame)

        # ── PAY / Clear buttons ───────────────────────────────────────────────
        btn_frame = QFrame()
        btn_frame.setFixedHeight(72)
        btn_frame.setStyleSheet("background:#111827;border-top:1px solid #1a3a5c;")
        bl = QHBoxLayout(btn_frame)
        bl.setContentsMargins(8, 10, 8, 10)
        bl.setSpacing(8)

        clear_btn = QPushButton("🧹")
        clear_btn.setFixedSize(52, 52)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setToolTip("Clear sale")
        clear_btn.setStyleSheet(
            "QPushButton{background:#b71c1c;color:#fff;font-size:20px;"
            "font-weight:700;border:none;border-radius:8px;}"
            "QPushButton:hover{background:#7f0000;}"
        )
        clear_btn.clicked.connect(lambda: self._pos._clear_all())
        bl.addWidget(clear_btn)

        print_btn = QPushButton("🖨")
        print_btn.setFixedSize(52, 52)
        print_btn.setCursor(Qt.PointingHandCursor)
        print_btn.setToolTip("Print last receipt")
        print_btn.setStyleSheet(
            "QPushButton{background:#37474f;color:#fff;font-size:20px;"
            "font-weight:700;border:none;border-radius:8px;}"
            "QPushButton:hover{background:#263238;}"
        )
        print_btn.clicked.connect(lambda: self._pos._print_last())
        bl.addWidget(print_btn)

        pay_btn = QPushButton("💳   PAY")
        pay_btn.setFixedHeight(52)
        pay_btn.setCursor(Qt.PointingHandCursor)
        pay_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:22px;"
            "font-weight:700;border:none;border-radius:8px;letter-spacing:2px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:pressed{background:#0a3d12;}"
        )
        pay_btn.clicked.connect(lambda: self._pos._do_pay())
        bl.addWidget(pay_btn, 2)

        lay.addWidget(btn_frame)
        return panel

    # ── Slot wiring ───────────────────────────────────────────────────────────

    def _on_item_selected(self, item_dict: dict):
        self._pos._on_touch_item(item_dict)

    # ── Public API called by POSScreen ────────────────────────────────────────

    def refresh_tiles(self):
        self._tile_panel.refresh()

    def refresh_cart(self):
        pos   = self._pos
        lines = pos._lines

        self._cust_lbl.setText(f"👤  {pos._customer_name}")

        # Rebuild line widgets (clear all except trailing stretch)
        layout = self._lines_layout
        while layout.count() > 1:
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        cur = getattr(pos, "_currency", "LBP")
        rate = getattr(pos, "_lbp_rate", 89_500) or 89_500
        sym = "$" if cur == "USD" else "ل.ل"

        if not lines:
            self._count_lbl.setText("No items")
            self._total_lbl.setText(f"{sym}  0")
            self._usd_lbl.setText("")
            return

        n = len(lines)
        self._count_lbl.setText(f"{n} line{'s' if n != 1 else ''}")

        for idx, line in enumerate(lines):
            layout.insertWidget(layout.count() - 1, self._make_line_widget(idx, line))

        # Totals
        subtotal = sum(l["qty"] * l["price"] * (1 - l["disc"] / 100) for l in lines)
        grand    = subtotal
        if cur == "USD":
            self._total_lbl.setText(f"$  {grand:,.2f}")
            lbp = grand * rate
            self._usd_lbl.setText(f"≈ ل.ل {lbp:,.0f}" if grand else "")
        else:
            self._total_lbl.setText(f"ل.ل  {grand:,.0f}")
            usd = grand / rate if grand else 0.0
            self._usd_lbl.setText(f"≈ $ {usd:,.2f}" if grand else "")

    def set_last_invoice(self, text: str):
        self._last_inv_lbl.setText(text if text and text != "—" else "—")

    def _scroll_to_bottom(self):
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── Cart line widget ──────────────────────────────────────────────────────

    def _make_line_widget(self, idx: int, line: dict) -> QWidget:
        item  = line["item"]
        qty   = line["qty"]
        total = qty * line["price"] * (1 - line["disc"] / 100)

        w = QFrame()
        w.setStyleSheet(
            "QFrame{background:#1e2a3a;border-radius:6px;border:1px solid #2a3a5a;}"
            "QLabel{background:transparent;border:none;}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        # Item name
        name_lbl = QLabel(item.description)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet("color:#e8f0fb;font-size:13px;font-weight:700;")
        lay.addWidget(name_lbl)

        # Controls: [−] qty [+]  ·  total  [×]
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        def _btn(text, bg, hover, w_=42, h_=42):
            b = QPushButton(text)
            b.setFixedSize(w_, h_)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{bg};color:#fff;font-size:18px;"
                f"font-weight:700;border:none;border-radius:6px;}}"
                f"QPushButton:hover{{background:{hover};}}"
            )
            return b

        minus = _btn("−", "#37474f", "#263238")
        minus.clicked.connect(lambda _, i=idx: self._pos.touch_qty_delta(i, -1))
        ctrl.addWidget(minus)

        qty_btn = QPushButton(f"{qty:g}")
        qty_btn.setFixedSize(54, 42)
        qty_btn.setCursor(Qt.PointingHandCursor)
        qty_btn.setStyleSheet(
            "QPushButton{color:#fff;font-size:16px;font-weight:700;"
            "background:#2a3a5a;border-radius:4px;border:1px solid #4a6a9a;}"
            "QPushButton:hover{background:#3a5a8a;}"
        )
        qty_btn.clicked.connect(lambda _, i=idx: self._edit_qty(i))
        ctrl.addWidget(qty_btn)

        plus = _btn("+", "#1a6cb5", "#1a3a5c")
        plus.clicked.connect(lambda _, i=idx: self._pos.touch_qty_delta(i, +1))
        ctrl.addWidget(plus)

        ctrl.addStretch()

        cur = getattr(self._pos, "_currency", "LBP")
        tot_lbl = QLabel(f"{'$' if cur == 'USD' else 'ل.ل'} {total:,.{'2' if cur == 'USD' else '0'}f}")
        tot_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tot_lbl.setStyleSheet("color:#00e676;font-size:13px;font-weight:700;")
        ctrl.addWidget(tot_lbl)

        ctrl.addSpacing(6)

        rm = _btn("×", "#c62828", "#7f0000", 36, 42)
        rm.clicked.connect(lambda _, i=idx: self._pos.touch_remove_line(i))
        ctrl.addWidget(rm)

        lay.addLayout(ctrl)
        return w

    def _edit_qty(self, idx: int):
        """Show a decimal numpad dialog to set an exact quantity for cart line idx."""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
        )
        from PySide6.QtCore import Qt

        lines = self._pos._lines
        if idx < 0 or idx >= len(lines):
            return
        item_name = lines[idx]["item"].description
        current   = lines[idx]["qty"]

        dlg = QDialog(self)
        dlg.setWindowTitle("Set Quantity")
        dlg.setFixedSize(280, 420)
        dlg.setStyleSheet("background:#1a2a3a;")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Item name
        name_lbl = QLabel(item_name)
        name_lbl.setWordWrap(True)
        name_lbl.setAlignment(Qt.AlignCenter)
        name_lbl.setStyleSheet("color:#a8c8e8;font-size:12px;font-weight:700;")
        root.addWidget(name_lbl)

        # Display
        disp = QLabel(f"{current:g}")
        disp.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        disp.setFixedHeight(56)
        disp.setStyleSheet(
            "color:#00e676;font-size:28px;font-weight:700;"
            "background:#0d1117;border-radius:6px;padding:0 12px;"
        )
        root.addWidget(disp)

        _val = [""]   # mutable buffer

        def _press(k):
            v = _val[0]
            if k == "⌫":
                v = v[:-1]
            elif k == "C":
                v = ""
            elif k == ".":
                if "." not in v:
                    v = v + "."
            else:
                v = v + k
            _val[0] = v
            disp.setText(v if v not in ("", ".") else "0")

        btn_s = (
            "QPushButton{background:#1e2a3a;color:#fff;font-size:20px;font-weight:700;"
            "border:1px solid #2a3a5a;border-radius:6px;}"
            "QPushButton:pressed{background:#2a4a6a;}"
        )
        red_s  = btn_s.replace("#1e2a3a", "#3a1010").replace("#2a3a5a", "#5a2020")
        back_s = btn_s.replace("#1e2a3a", "#2a2010").replace("#2a3a5a", "#5a4020")

        grid = [["7","8","9"], ["4","5","6"], ["1","2","3"], ["C","0","⌫"], [".","","OK"]]
        styles = {"C": red_s, "⌫": back_s}

        for row_keys in grid:
            row = QHBoxLayout()
            row.setSpacing(8)
            for k in row_keys:
                if k == "":
                    row.addStretch(1)
                    continue
                b = QPushButton(k)
                b.setFixedHeight(52)
                if k == "OK":
                    b.setStyleSheet(
                        "QPushButton{background:#1a6cb5;color:#fff;font-size:16px;"
                        "font-weight:700;border:none;border-radius:6px;}"
                        "QPushButton:pressed{background:#0d47a1;}"
                    )
                    def _confirm():
                        txt = _val[0].strip(".")
                        try:
                            new_qty = float(txt) if txt else current
                        except ValueError:
                            new_qty = current
                        if new_qty > 0:
                            self._pos.touch_qty_set(idx, new_qty)
                        dlg.accept()
                    b.clicked.connect(_confirm)
                else:
                    b.setStyleSheet(styles.get(k, btn_s))
                    b.clicked.connect(lambda _, v=k: _press(v))
                row.addWidget(b, 1)
            root.addLayout(row)

        dlg.exec()
