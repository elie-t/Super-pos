"""
Barcode Print screen — search items, build a print queue, print labels on any
system printer (thermal label printer, Zebra, Dymo, etc.)

Requires:  pip install python-barcode
Labels are rendered as QImages at 203 DPI (standard thermal) and sent to the
selected printer one label per page, so label printers advance one sticker at
a time.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QComboBox, QSpinBox, QCheckBox,
    QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSizeF, QMarginsF, QRectF
from PySide6.QtGui import QPageSize, QPageLayout
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

_LABEL_DPI = 203          # render resolution — matches standard thermal printers
_MM_TO_PX  = _LABEL_DPI / 25.4


class BarcodePrintScreen(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._print_queue: list[dict] = []
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._load_items)
        self._build_ui()
        self._load_categories()
        self._load_items()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # Title
        title_row = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("secondaryBtn")
        back_btn.setFixedSize(80, 30)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        title = QLabel("Barcode Print")
        title.setObjectName("sectionTitle")
        title_row.addWidget(back_btn)
        title_row.addSpacing(8)
        title_row.addWidget(title)
        title_row.addStretch()
        root.addLayout(title_row)

        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(5)
        root.addWidget(splitter)

        # ── Top: item search + table ──────────────────────────────────────────
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)

        sr = QHBoxLayout()
        self._name_box = QLineEdit()
        self._name_box.setObjectName("searchBox")
        self._name_box.setPlaceholderText("🔍 Name or code…")
        self._name_box.setFixedHeight(32)
        self._name_box.textChanged.connect(self._search_timer.start)
        self._bc_box = QLineEdit()
        self._bc_box.setObjectName("searchBox")
        self._bc_box.setPlaceholderText("🔍 Barcode…")
        self._bc_box.setFixedHeight(32)
        self._bc_box.textChanged.connect(self._search_timer.start)
        self._cat_combo = QComboBox()
        self._cat_combo.setFixedHeight(32)
        self._cat_combo.setMinimumWidth(140)
        self._cat_combo.currentIndexChanged.connect(self._load_items)
        add_btn = QPushButton("Add to Queue →")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(32)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_selected)
        sr.addWidget(self._name_box, 3)
        sr.addWidget(self._bc_box, 2)
        sr.addWidget(self._cat_combo, 2)
        sr.addWidget(add_btn)
        tl.addLayout(sr)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Code", "Barcode", "Name", "Category", "Price"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.doubleClicked.connect(self._add_selected)
        tl.addWidget(self._table)

        tl.addWidget(self._small_hint("Double-click or select rows → 'Add to Queue →'"))
        splitter.addWidget(top)

        # ── Bottom: queue + print settings ───────────────────────────────────
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 4, 0, 0)
        bl.setSpacing(6)

        qh = QHBoxLayout()
        self._queue_lbl = QLabel("Print Queue  (0 items · 0 labels)")
        self._queue_lbl.setStyleSheet("font-weight:700; color:#1a3a5c;")
        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("warningBtn")
        clear_btn.setFixedHeight(26)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_queue)
        qh.addWidget(self._queue_lbl)
        qh.addStretch()
        qh.addWidget(clear_btn)
        bl.addLayout(qh)

        self._q_table = QTableWidget()
        self._q_table.setColumnCount(5)
        self._q_table.setHorizontalHeaderLabels(["Code", "Barcode", "Name", "Price", "Qty"])
        self._q_table.setAlternatingRowColors(True)
        self._q_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._q_table.verticalHeader().setVisible(False)
        self._q_table.setFixedHeight(130)
        qh2 = self._q_table.horizontalHeader()
        qh2.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4):
            qh2.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._q_table.doubleClicked.connect(self._remove_from_queue)
        bl.addWidget(self._q_table)
        bl.addWidget(self._small_hint("Double-click a queue row to remove it"))

        # Print settings row
        pr = QHBoxLayout()
        pr.setSpacing(10)

        pr.addWidget(QLabel("Printer:"))
        self._printer_combo = QComboBox()
        self._printer_combo.setMinimumWidth(200)
        self._printer_combo.setFixedHeight(30)
        for info in QPrinterInfo.availablePrinters():
            self._printer_combo.addItem(info.printerName())
        # Pre-select a likely barcode printer
        for k in ("zebra", "dymo", "tsc", "label", "barcode", "bixolon", "brother", "xp-"):
            for i in range(self._printer_combo.count()):
                if k in self._printer_combo.itemText(i).lower():
                    self._printer_combo.setCurrentIndex(i)
                    break
            else:
                continue
            break
        pr.addWidget(self._printer_combo)

        pr.addWidget(QLabel("Label (mm):"))
        self._lbl_w = QSpinBox()
        self._lbl_w.setRange(20, 200)
        self._lbl_w.setValue(30)
        self._lbl_w.setFixedSize(55, 30)
        self._lbl_w.setToolTip("Label width in mm")
        pr.addWidget(self._lbl_w)
        pr.addWidget(QLabel("×"))
        self._lbl_h = QSpinBox()
        self._lbl_h.setRange(10, 200)
        self._lbl_h.setValue(20)
        self._lbl_h.setFixedSize(55, 30)
        self._lbl_h.setToolTip("Label height in mm")
        pr.addWidget(self._lbl_h)

        self._show_price_chk = QCheckBox("Show price")
        self._show_price_chk.setChecked(True)
        pr.addWidget(self._show_price_chk)

        pr.addWidget(QLabel("Currency:"))
        self._currency_combo = QComboBox()
        self._currency_combo.addItems(["USD", "LBP"])
        self._currency_combo.setFixedHeight(30)
        pr.addWidget(self._currency_combo)

        pr.addStretch()

        self._print_btn = QPushButton("🖨  Print Labels")
        self._print_btn.setObjectName("primaryBtn")
        self._print_btn.setFixedHeight(36)
        self._print_btn.setMinimumWidth(140)
        self._print_btn.setCursor(Qt.PointingHandCursor)
        self._print_btn.clicked.connect(self._do_print)
        pr.addWidget(self._print_btn)

        bl.addLayout(pr)
        splitter.addWidget(bottom)
        splitter.setSizes([420, 270])

    @staticmethod
    def _small_hint(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#999; font-size:10px;")
        return lbl

    # ── Data ──────────────────────────────────────────────────────────────────

    def _load_categories(self):
        self._cat_combo.addItem("All Categories", None)
        try:
            from database.engine import get_session, init_db
            from database.models.items import Category
            init_db()
            s = get_session()
            try:
                for c in s.query(Category).order_by(Category.name).all():
                    self._cat_combo.addItem(c.name, c.id)
            finally:
                s.close()
        except Exception:
            pass

    def _load_items(self):
        try:
            from database.engine import get_session, init_db
            from database.models.items import Item, ItemBarcode
            import sqlalchemy as sa

            name_q = self._name_box.text().strip()
            bc_q   = self._bc_box.text().strip()
            cat_id = self._cat_combo.currentData()

            init_db()
            s = get_session()
            try:
                q = s.query(Item).filter_by(is_active=True)
                if name_q:
                    q = q.filter(sa.or_(
                        Item.name.ilike(f"%{name_q}%"),
                        Item.code.ilike(f"%{name_q}%"),
                    ))
                if bc_q:
                    q = q.join(Item.barcodes).filter(
                        ItemBarcode.barcode.ilike(f"%{bc_q}%")
                    )
                if cat_id:
                    q = q.filter_by(category_id=cat_id)

                self._table.setRowCount(0)
                for item in q.order_by(Item.name).limit(300).all():
                    bc = item.primary_barcode or ""
                    price_str = ""
                    for p in item.prices:
                        if p.price_type == "retail" and p.is_active:
                            price_str = (
                                f"{p.amount:,.0f} L"
                                if p.currency == "LBP"
                                else f"$ {p.amount:.2f}"
                            )
                            break
                    cat_nm = item.category.name if item.category else ""
                    row = self._table.rowCount()
                    self._table.insertRow(row)
                    for col, val in enumerate([item.code, bc, item.name, cat_nm, price_str]):
                        self._table.setItem(row, col, QTableWidgetItem(val))
                    self._table.item(row, 0).setData(Qt.UserRole, {
                        "id":      item.id,
                        "code":    item.code,
                        "barcode": bc,
                        "name":    item.name,
                        "price_str": price_str,
                        "prices": [
                            (p.price_type, p.amount, p.currency)
                            for p in item.prices if p.is_active
                        ],
                    })
            finally:
                s.close()
        except Exception:
            pass

    def refresh(self):
        self._load_items()

    # ── Queue management ──────────────────────────────────────────────────────

    def _add_selected(self):
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows and self._table.currentRow() >= 0:
            rows = {self._table.currentRow()}
        for row in sorted(rows):
            cell = self._table.item(row, 0)
            if not cell:
                continue
            info = cell.data(Qt.UserRole)
            if not info:
                continue
            existing = next((q for q in self._print_queue if q["id"] == info["id"]), None)
            if existing:
                existing["qty"] = min(existing["qty"] + 1, 99)
            else:
                self._print_queue.append({**info, "qty": 1})
        self._refresh_queue()

    def _remove_from_queue(self):
        row = self._q_table.currentRow()
        if 0 <= row < len(self._print_queue):
            del self._print_queue[row]
            self._refresh_queue()

    def _clear_queue(self):
        self._print_queue.clear()
        self._refresh_queue()

    def _refresh_queue(self):
        self._q_table.setRowCount(0)
        total = sum(q["qty"] for q in self._print_queue)
        self._queue_lbl.setText(
            f"Print Queue  ({len(self._print_queue)} items · {total} labels)"
        )
        for i, entry in enumerate(self._print_queue):
            self._q_table.insertRow(i)
            for col, val in enumerate([
                entry["code"], entry["barcode"], entry["name"], entry["price_str"]
            ]):
                self._q_table.setItem(i, col, QTableWidgetItem(val))
            spin = QSpinBox()
            spin.setRange(1, 99)
            spin.setValue(entry["qty"])
            spin.setFixedHeight(22)
            spin.valueChanged.connect(lambda v, idx=i: self._set_qty(idx, v))
            self._q_table.setCellWidget(i, 4, spin)

    def _set_qty(self, idx: int, val: int):
        if idx < len(self._print_queue):
            self._print_queue[idx]["qty"] = val
            total = sum(q["qty"] for q in self._print_queue)
            self._queue_lbl.setText(
                f"Print Queue  ({len(self._print_queue)} items · {total} labels)"
            )

    # ── Printing ───────────────────────────────────────────────────────────────

    def _do_print(self):
        if not self._print_queue:
            QMessageBox.information(self, "Print", "No items in the print queue.")
            return

        try:
            import barcode as _bc_check  # noqa: F401
        except ImportError:
            QMessageBox.critical(
                self, "Missing dependency",
                "python-barcode is not installed.\n\n"
                "Run:  pip install python-barcode\n"
                "then restart the application."
            )
            return

        currency   = self._currency_combo.currentText()
        show_price = self._show_price_chk.isChecked()
        w_mm = self._lbl_w.value()
        h_mm = self._lbl_h.value()

        labels: list[dict] = []
        for entry in self._print_queue:
            price_text = ""
            if show_price:
                for pt, amount, curr in entry.get("prices", []):
                    if pt == "retail" and curr == currency:
                        price_text = (
                            f"{amount:,.0f} L" if curr == "LBP" else f"$ {amount:.2f}"
                        )
                        break
                if not price_text and entry.get("price_str"):
                    price_text = entry["price_str"]
            for _ in range(entry["qty"]):
                labels.append({
                    "name":    entry["name"],
                    "barcode": entry["barcode"],
                    "code":    entry["code"],
                    "price":   price_text,
                })

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer_name = self._printer_combo.currentText()
        if printer_name:
            printer.setPrinterName(printer_name)
        printer.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter))
        printer.setFullPage(True)
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)

        try:
            self._send_to_printer(printer, labels, w_mm, h_mm)
            QMessageBox.information(
                self, "Done",
                f"Sent {len(labels)} label(s) to '{printer_name}'."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Print Error", str(exc))

    def _send_to_printer(
        self,
        printer: QPrinter,
        labels: list[dict],
        w_mm: float,
        h_mm: float,
    ):
        from PySide6.QtGui import QPainter

        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        painter = QPainter(printer)
        for i, label in enumerate(labels):
            if i > 0:
                printer.newPage()
            img = self._render_label(label, w_mm, h_mm)
            painter.drawImage(page_rect, img)
        painter.end()

    # ── Label renderer ─────────────────────────────────────────────────────────

    def _render_label(self, label: dict, w_mm: float, h_mm: float):
        """
        Three-zone layout: name (top 30%) | barcode (middle 50%) | number+price (bottom 20%).
        Each zone is sized explicitly so no element ever overlaps another.
        """
        from PySide6.QtGui import QPainter, QImage, QFont, QFontMetrics
        from PySide6.QtCore import Qt as Qt_, QRectF

        W   = int(w_mm * _MM_TO_PX)
        H   = int(h_mm * _MM_TO_PX)
        PAD = max(int(_MM_TO_PX * 0.4), 3)

        img = QImage(W, H, QImage.Format.Format_ARGB32)
        img.setDotsPerMeterX(round(_LABEL_DPI / 0.0254))
        img.setDotsPerMeterY(round(_LABEL_DPI / 0.0254))
        img.fill(Qt_.white)

        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        name   = label.get("name", "").upper()
        bc_str = label.get("barcode", "").strip()
        price  = label.get("price", "")

        # ── Zone boundaries ───────────────────────────────────────────────────
        name_zone_h = max(int(H * 0.30), 24)
        bot_zone_h  = max(int(H * 0.20), 16)
        bc_zone_h   = H - name_zone_h - bot_zone_h   # middle gets what's left

        # ── Name zone (top) ───────────────────────────────────────────────────
        # Font: half the zone height (2 lines), capped so wide labels stay readable
        name_px = max(min(name_zone_h // 2 - 2, int(W * 0.065)), 8)
        name_font = QFont("Arial")
        name_font.setBold(True)
        name_font.setPixelSize(name_px)
        p.setFont(name_font)
        fm = QFontMetrics(name_font)

        wrapped = self._wrap_text(name, fm, W - PAD * 2)[:2]
        block_h = len(wrapped) * (fm.height() + 1)
        y_txt   = PAD + max((name_zone_h - block_h) // 2, 0)
        for line in wrapped:
            p.drawText(QRectF(0, y_txt, W, fm.height() + 2), Qt_.AlignCenter, line)
            y_txt += fm.height() + 1

        # ── Barcode zone (middle) ─────────────────────────────────────────────
        if bc_str:
            try:
                import barcode as _bc_lib
                from barcode.writer import ImageWriter
                from PIL import Image, ImageChops

                bc_obj = _bc_lib.get("code128", bc_str, writer=ImageWriter())
                options = {
                    "module_height": 10.0,   # mm — gives a good width:height ratio
                    "module_width":  0.6,    # mm
                    "quiet_zone":    0.5,
                    "write_text":    False,
                    "background":    "white",
                    "foreground":    "black",
                }
                pil_img = bc_obj.render(options)

                bg   = Image.new(pil_img.mode, pil_img.size, pil_img.getpixel((0, 0)))
                diff = ImageChops.difference(pil_img, bg)
                bbox = diff.getbbox()
                if bbox:
                    pil_img = pil_img.crop(bbox)

                pil_img = pil_img.convert("RGBA")
                data    = pil_img.tobytes("raw", "RGBA")
                q_bc    = QImage(data, pil_img.width, pil_img.height,
                                 QImage.Format.Format_RGBA8888).copy()

                aspect = pil_img.width / pil_img.height
                # Fixed margins: BC_L pushes barcode right, BC_R keeps price visible
                BC_L  = max(int(W * 0.15), 22)   # ~6 mm on 40 mm → pushed right
                BC_R  = max(int(W * 0.05), 8)    # ~2 mm right margin
                max_w = W - BC_L - BC_R           # narrower → bars closer together
                max_h = bc_zone_h - 2

                bc_w = max_w
                bc_h = int(bc_w / aspect)
                bc_h = max(bc_h, int(max_h * 0.70))
                if bc_h > max_h:
                    bc_h = max_h
                    bc_w = int(bc_h * aspect)
                bc_w = min(bc_w, max_w)

                x_bc = BC_L                                      # start after left margin
                y_bc = name_zone_h + (bc_zone_h - bc_h) // 2   # centered in zone

                p.drawImage(QRectF(float(x_bc), float(y_bc), float(bc_w), float(bc_h)), q_bc)

            except Exception as e:
                print(f"Barcode Render Error: {e}")

        # ── Bottom zone: barcode number + price ───────────────────────────────
        bot_px   = max(min(bot_zone_h - 4, 18), 9)
        bot_font = QFont("Arial")
        bot_font.setPixelSize(bot_px)
        bfm  = QFontMetrics(bot_font)
        bot_y = H - bot_zone_h + (bot_zone_h - bfm.height()) // 2
        p.setFont(bot_font)

        # Barcode number — centered across the full label width
        p.drawText(
            QRectF(0, bot_y, W, bfm.height()),
            Qt_.AlignCenter | Qt_.AlignVCenter,
            bc_str,
        )
        if price:
            pf = QFont("Arial")
            pf.setBold(True)
            pf.setPixelSize(bot_px)
            p.setFont(pf)
            price_r = max(int(W * 0.05), 8)   # same right margin as barcode (BC_R)
            p.drawText(
                QRectF(0, bot_y, W - price_r, bfm.height()),
                Qt_.AlignRight | Qt_.AlignVCenter,
                price,
            )

        p.end()
        return img

    @staticmethod
    def _wrap_text(text: str, fm: "QFontMetrics", max_w: int) -> list[str]:
        if fm.horizontalAdvance(text) <= max_w:
            return [text]
        words, lines, current = text.split(), [], ""
        for word in words:
            test = f"{current} {word}".strip()
            if fm.horizontalAdvance(test) <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [text]
