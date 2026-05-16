"""
POS Receipt Printer
====================
Renders an 80 mm thermal-style receipt using Qt's print system.
Works with any printer the OS knows about (thermal, laser, PDF).
"""
from __future__ import annotations

from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog, QPrinterInfo
from PySide6.QtGui import QTextDocument, QPageSize, QPageLayout
from PySide6.QtCore import QSizeF, QMarginsF

# 80 mm paper → 72 mm printable → 576 dots @ 203 dpi → 48 chars (Font A 12-dot)
CHARS_PER_LINE = 48   # conservative safe width for 80mm / 203dpi printers


def _build_receipt_lines(data: dict, payment_method: str, tendered: float,
                          width: int = CHARS_PER_LINE) -> list:
    """Return list of (text, is_bold) tuples — used by QPainter and plain-text renderers."""
    W        = width
    currency = data.get("currency", "LBP")
    is_lbp   = currency == "LBP"

    def fmt(v: float) -> str:
        return f"{v:,.0f} LBP" if is_lbp else f"$ {v:,.2f}"

    def rrow(label: str, value: str) -> str:
        value = str(value)
        vw    = len(value)
        lw    = W - vw
        label = label[:lw]
        return f"{label:<{lw}}{value}"

    rows: list[tuple[str, bool]] = []  # (text, bold)

    def add(text: str, bold: bool = False):
        rows.append((text, bold))

    # Header
    add(data.get("shop_name", "Shop").center(W))
    if data.get("shop_address"):
        add(data["shop_address"].center(W))
    if data.get("shop_phone"):
        add(f"Tel: {data['shop_phone']}".center(W))
    if data.get("warehouse") and data.get("warehouse") != data.get("shop_address"):
        add(data["warehouse"].center(W))
    add("-" * W)

    # Meta
    add(rrow("Receipt #:", data.get("invoice_number", "")))
    add(rrow("Date:",      data.get("sale_datetime") or data.get("date", "")))
    add(rrow("Cashier:",   data.get("cashier", "")))
    if data.get("customer"):
        add(rrow("Customer:", data["customer"]))
    add("-" * W)

    # Items — two-line format: name (bold) then qty x price → total (normal)
    for li in data.get("lines", []):
        desc  = str(li.get("description", ""))
        qty   = li.get("qty",        0)
        price = li.get("unit_price", 0.0)
        total = li.get("total",      0.0)
        disc  = li.get("disc_pct",   0.0)

        # Name line — bold; wrap if needed
        first = True
        while desc:
            add(desc[:W], bold=first)
            desc  = desc[W:]
            first = False

        # Detail line: "  qty x price" right-aligned with total
        qty_str  = f"{qty:g}"
        disc_tag = f" (-{disc:.0f}%)" if disc else ""
        detail   = f"  {qty_str} x {fmt(price)}{disc_tag}"
        add(rrow(detail, fmt(total)))

    # Totals
    add("-" * W)
    add(rrow("Subtotal:", fmt(data.get("subtotal", 0.0))))
    if data.get("discount", 0.0):
        add(rrow("Discount:", f"-{fmt(data['discount'])}"))
    if data.get("vat", 0.0):
        add(rrow("VAT (11%):", fmt(data.get("vat", 0.0))))
    add("=" * W)
    add(rrow("TOTAL:", fmt(data.get("total", 0.0))), bold=True)
    line_count = len(data.get("lines", []))
    add(rrow("Lines:", str(line_count)))

    method_label = {"cash": "Cash", "card": "Card", "account": "Account"}.get(
        payment_method, payment_method.capitalize()
    )
    add(rrow(f"Paid ({method_label}):", fmt(data.get("amount_paid", 0.0))))

    change = max(0.0, tendered - data.get("total", 0.0)) if payment_method == "cash" else 0.0
    if change > 0:
        add(rrow("Change:", fmt(change)), bold=True)

    # USD equivalent for LBP invoices
    lbp_rate  = int(data.get("lbp_rate") or 0)
    inv_total = data.get("total", 0.0)
    if is_lbp and inv_total and lbp_rate:
        usd_equiv = inv_total / lbp_rate
        add(rrow("= USD:", f"$ {usd_equiv:,.2f}"))

    # Footer
    add("-" * W)
    footer = data.get("receipt_footer", "Thank you!")
    if footer:
        add(footer.center(W))

    return rows


def _build_receipt_text(data: dict, payment_method: str, tendered: float,
                        width: int = CHARS_PER_LINE) -> str:
    """Build a plain-text receipt string — used for HTML <pre> and ESC/POS."""
    return "\n".join(t for t, _ in _build_receipt_lines(data, payment_method, tendered, width))


def _build_html(data: dict, payment_method: str, tendered: float) -> str:
    """Styled header + <pre> body — big shop name, no HTML table kerning artifacts."""
    import html as _h

    def e(s): return _h.escape(str(s))

    # Add LBP rate to data so _build_receipt_text can use it for USD equivalent
    if not data.get("lbp_rate"):
        try:
            from database.engine import get_session, init_db
            from database.models.items import Setting
            init_db()
            _sess = get_session()
            try:
                _r = _sess.get(Setting, "lbp_rate")
                data = dict(data, lbp_rate=int(_r.value) if _r and _r.value else 0)
            finally:
                _sess.close()
        except Exception:
            pass

    # ── Styled header (shop name big, address/phone smaller) ──────────────────
    header = (
        f"<div style='text-align:center;font-family:monospace;font-size:12pt;"
        f"font-weight:700;letter-spacing:1px;margin-bottom:1px;'>{e(data.get('shop_name',''))}</div>"
    )
    if data.get("shop_address"):
        header += f"<div style='text-align:center;font-family:monospace;font-size:6.5pt;line-height:1.2;'>{e(data['shop_address'])}</div>"
    if data.get("shop_phone"):
        header += f"<div style='text-align:center;font-family:monospace;font-size:6.5pt;line-height:1.2;'>Tel: {e(data['shop_phone'])}</div>"
    if data.get("warehouse") and data.get("warehouse") != data.get("shop_address"):
        header += f"<div style='text-align:center;font-family:monospace;font-size:6.5pt;line-height:1.2;'>{e(data['warehouse'])}</div>"

    # ── Body: plain text starting from the first separator ────────────────────
    full_text = _build_receipt_text(data, payment_method, tendered)
    # _build_receipt_text includes the header lines; strip them (everything up
    # to and including the first "-" separator line) since we render it above.
    sep_line = "-" * CHARS_PER_LINE
    idx = full_text.find(sep_line)
    body_text = full_text[idx:] if idx >= 0 else full_text

    escaped = _h.escape(body_text)
    return (
        "<html dir='ltr'><head><meta charset='utf-8'></head>"
        "<body dir='ltr' style='margin:0;padding:0;'>"
        f"{header}"
        f"<pre style='font-family:monospace;font-size:6.5pt;line-height:1.15;"
        f"white-space:pre;margin:0;padding:0;color:#000;'>{escaped}</pre>"
        "</body></html>"
    )


def _is_escpos_configured() -> bool:
    """Return True if an ESC/POS printer type is saved in settings (no device open)."""
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            s = session.get(Setting, "escpos_type")
            return bool(s and s.value and s.value != "windows_qt")
        finally:
            session.close()
    except Exception:
        pass
    return False


def _get_qt_printer_name() -> str:
    """Return the Windows Qt system printer name from settings, or '' if not configured."""
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            ptype = session.get(Setting, "escpos_type")
            if ptype and ptype.value == "windows_qt":
                s = session.get(Setting, "escpos_qt_printer")
                return s.value if s else ""
        finally:
            session.close()
    except Exception:
        pass
    return ""


def print_receipt(
    data: dict,
    payment_method: str = "cash",
    tendered: float = 0.0,
    parent=None,
    show_preview: bool = True,
) -> None:
    """
    Print a POS receipt.
    Priority:
      1. ESC/POS printer (configured in Settings) → direct thermal print
      2. Windows system printer (windows_qt type) → auto-print via Qt, no dialog
      3. Fallback → Qt print preview dialog
    """
    from PySide6.QtWidgets import QMessageBox

    # ── 1. Try ESC/POS direct print ────────────────────────────────────────
    try:
        p = get_escpos_printer()
        if p is not None:
            ok, err = print_receipt_escpos(data, payment_method, tendered)
            if not ok and parent:
                QMessageBox.warning(parent, "Printer Error", err)
            return
    except Exception as exc:
        if parent:
            QMessageBox.warning(parent, "Printer Error", str(exc))
        return

    # ── 2. Windows Qt system printer — auto-print, no dialog ───────────────
    qt_name = _get_qt_printer_name()
    if qt_name:
        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        printer.setPrinterName(qt_name)
        # Do NOT force a custom page size — use whatever the printer has configured
        # in Windows. Forcing 80mm when the driver expects a different size causes
        # an offset/centering that produces the large left gap.
        printer.setFullPage(False)
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        _render_to_printer(None, printer, receipt_data=data,
                           payment_method=payment_method, tendered=tendered)
        return

    # ── 3. No printer configured — show Qt preview dialog ──────────────────
    printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
    printer.setPageSize(QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter))
    printer.setFullPage(True)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    _try_set_thermal_printer(printer)

    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle("Receipt Preview")
    dlg.paintRequested.connect(
        lambda p: _render_to_printer(None, p, receipt_data=data,
                                     payment_method=payment_method, tendered=tendered)
    )
    dlg.exec()


def _render_to_printer(html_or_data, printer: QPrinter, receipt_data: dict = None,
                        payment_method: str = "cash", tendered: float = 0.0) -> None:
    """Render a receipt to printer using QPainter directly — bypasses Qt HTML kerning bugs."""
    from PySide6.QtGui import QPainter, QFont, QFontMetrics
    from PySide6.QtCore import Qt as _Qt, QRectF

    page_pt  = printer.pageRect(QPrinter.Unit.Point)
    page_w   = page_pt.width()
    page_h   = page_pt.height()
    scale    = printer.resolution() / 72.0

    painter  = QPainter(printer)
    painter.scale(scale, scale)

    # ── Title font (shop name) ────────────────────────────────────────────────
    title_font = QFont("Courier New")
    title_font.setPointSizeF(11.0)
    title_font.setBold(True)
    title_font.setKerning(False)
    title_font.setFixedPitch(True)

    # ── Body font ─────────────────────────────────────────────────────────────
    body_font = QFont("Courier New")
    body_font.setPointSizeF(7.0)
    body_font.setBold(False)
    body_font.setKerning(False)
    body_font.setFixedPitch(True)

    # Measure actual char width from the printer device so the text line
    # is always built to fit — avoids right-side clipping on thermal drivers.
    painter.setFont(body_font)
    _fm     = painter.fontMetrics()          # logical-unit metrics after scale
    _char_w = _fm.horizontalAdvance("M")     # width of one monospace char (pts)
    # Leave a small right margin (3 chars) so driver rounding never clips
    qt_chars = max(32, min(CHARS_PER_LINE, int(page_w / _char_w) - 3))

    title_h = QFontMetrics(title_font).height()
    body_h  = QFontMetrics(body_font).height()
    line_h  = body_h * 1.1

    y    = 0.0
    page = 0

    def _new_page_if_needed(needed):
        nonlocal y, page
        if y + needed > page_h:
            printer.newPage()
            y = 0.0
            page += 1

    def _draw(text, font, align=_Qt.AlignLeft, bold=False):
        nonlocal y
        f = QFont(font)
        f.setBold(bold)
        painter.setFont(f)
        h = QFontMetrics(f).height() * 1.1
        _new_page_if_needed(h)
        painter.drawText(QRectF(0, y, page_w, h), align | _Qt.AlignTop, text)
        y += h

    # If called with receipt_data, build plain text from scratch
    if receipt_data is not None:
        data = receipt_data
        # Ensure lbp_rate is available for USD equivalent line
        if not data.get("lbp_rate"):
            try:
                from database.engine import get_session, init_db
                from database.models.items import Setting
                init_db()
                _sess = get_session()
                try:
                    _r = _sess.get(Setting, "lbp_rate")
                    data = dict(data, lbp_rate=int(_r.value) if _r and _r.value else 0)
                finally:
                    _sess.close()
            except Exception:
                pass
        currency  = data.get("currency", "LBP")
        is_lbp    = currency == "LBP"

        def fmt(v): return f"{v:,.0f} L" if is_lbp else f"$ {v:,.2f}"

        # Header
        _draw(data.get("shop_name", ""), title_font, _Qt.AlignHCenter)
        if data.get("shop_address"):
            _draw(data["shop_address"], body_font, _Qt.AlignHCenter)
        if data.get("shop_phone"):
            _draw(f"Tel: {data['shop_phone']}", body_font, _Qt.AlignHCenter)
        if data.get("warehouse") and data.get("warehouse") != data.get("shop_address"):
            _draw(data["warehouse"], body_font, _Qt.AlignHCenter)

        # Build body lines with bold markers — use measured line width
        all_lines = _build_receipt_lines(data, payment_method, tendered, width=qt_chars)
        # Strip header section (up to and including the first separator)
        sep_text = "-" * qt_chars
        body_lines = all_lines
        for i, (txt, _) in enumerate(all_lines):
            if txt == sep_text:
                body_lines = all_lines[i:]  # keep from first separator onward
                break

        bold_body = QFont(body_font)
        bold_body.setBold(True)

        for txt, is_bold in body_lines:
            _new_page_if_needed(line_h)
            painter.setFont(bold_body if is_bold else body_font)
            painter.drawText(QRectF(0, y, page_w, line_h), _Qt.AlignLeft | _Qt.AlignTop, txt)
            y += line_h
    else:
        # Fallback: render html string via QTextDocument (legacy / transfer receipts)
        from PySide6.QtGui import QTextOption
        from PySide6.QtCore import QRectF as _QRectF
        doc = QTextDocument()
        doc.setDocumentMargin(2)
        opt = QTextOption()
        opt.setTextDirection(_Qt.LeftToRight)
        doc.setDefaultTextOption(opt)
        doc.setHtml(html_or_data)
        doc.setTextWidth(page_w)
        total_h = doc.size().height()
        yy = 0.0
        pg = 0
        while yy < total_h:
            if pg > 0:
                printer.newPage()
            painter.save()
            painter.translate(0.0, -yy)
            doc.drawContents(painter, _QRectF(0, yy, page_w, page_h))
            painter.restore()
            yy += page_h
            pg += 1

    painter.end()


def _try_set_thermal_printer(printer: QPrinter) -> None:
    keywords = ("thermal", "pos", "receipt", "80mm", "80 mm", "escpos", "tm-", "xp-", "rp-")
    for info in QPrinterInfo.availablePrinters():
        name_lower = info.printerName().lower()
        if any(k in name_lower for k in keywords):
            printer.setPrinterName(info.printerName())
            return


# ── ESC/POS direct thermal printing ──────────────────────────────────────────
def get_escpos_printer():
    """
    Return a configured python-escpos printer instance, or None.
    Reads connection type and parameters from the Settings table.
    """
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            def _get(key, default=""):
                s = session.get(Setting, key)
                return s.value if s else default

            ptype = _get("escpos_type", "")
            if not ptype:
                return None

            if ptype == "usb_auto":
                import usb.core
                from escpos.printer import Usb
                dev = usb.core.find(find_all=False, bDeviceClass=7)  # USB printer class
                if dev is None:
                    # Fallback: first device with known POS vendor IDs
                    POS_VENDORS = (0x04b8, 0x0519, 0x1504, 0x1d90, 0x0dd4, 0x0fe6)
                    for vid in POS_VENDORS:
                        dev = usb.core.find(idVendor=vid)
                        if dev:
                            break
                if dev:
                    return Usb(dev.idVendor, dev.idProduct)
                return None

            elif ptype == "usb_manual":
                vid = int(_get("escpos_usb_vid", "0x0000"), 16)
                pid = int(_get("escpos_usb_pid", "0x0000"), 16)
                if vid and pid:
                    from escpos.printer import Usb
                    return Usb(vid, pid)

            elif ptype == "network":
                host = _get("escpos_host", "")
                port = int(_get("escpos_port", "9100"))
                if host:
                    from escpos.printer import Network
                    return Network(host, port=port)

            elif ptype == "serial":
                devfile = _get("escpos_serial", "/dev/ttyUSB0")
                baud    = int(_get("escpos_baud", "9600"))
                from escpos.printer import Serial
                return Serial(devfile, baudrate=baud)

            elif ptype == "win_raw":
                name = _get("escpos_win_printer", "")
                if name:
                    from escpos.printer import Win32Raw
                    return Win32Raw(name)

            elif ptype == "file":
                path = _get("escpos_file", "/dev/usb/lp0")
                from escpos.printer import File
                return File(path)

        finally:
            session.close()
    except Exception:
        pass
    return None


def _escpos_row(name: str, right: str, name_w: int, right_w: int) -> str:
    """Format one table row: name left-padded, right value right-padded."""
    right = right[:right_w]
    if len(name) <= name_w:
        return f"{name:<{name_w}}{right:>{right_w}}\n"
    # Long name: print first chunk with value, then continuation lines
    out = f"{name[:name_w]}{right:>{right_w}}\n"
    rest = name[name_w:]
    W = name_w + right_w
    while rest:
        out += f"  {rest[:W - 2]}\n"
        rest = rest[W - 2:]
    return out


def _build_transfer_html(
    no: str, from_wh: str, to_wh: str, date_str: str,
    lines: list, currency: str = "",
) -> str:
    """Build an HTML receipt for a warehouse transfer — name | qty rows, grand total only."""
    import html as _h

    def e(s) -> str:
        return _h.escape(str(s))

    total = sum(float(l.get("total", 0)) for l in lines)
    is_lbp = currency == "LBP"

    def fmt(v: float) -> str:
        return f"{v:,.0f} LBP" if is_lbp else f"$ {v:,.2f}"

    L  = "width:72%;padding:1px 2px 1px 0;white-space:normal;word-break:break-word;vertical-align:top;"
    R  = "width:28%;text-align:right;padding:1px 0 1px 2px;white-space:nowrap;vertical-align:top;"
    HL = "width:72%;padding:0 2px 2px 0;font-weight:700;"
    HR = "width:28%;text-align:right;padding:0 0 2px 2px;font-weight:700;"
    SEP = "<tr><td colspan='2' style='border-top:1px dashed #000;padding:0;height:2px;font-size:1pt;'></td></tr>"
    SEP2 = "<tr><td colspan='2' style='border-top:1px solid #000;padding:0;height:2px;font-size:1pt;'></td></tr>"

    header = (
        "<div style='text-align:center;font-size:13pt;font-weight:700;'>Warehouse Transfer</div>"
        f"<div style='text-align:center;font-size:11pt;font-weight:700;'>{e(no)}</div>"
        f"<div style='text-align:center;font-size:9pt;line-height:1.3;'>{e(from_wh)} &rarr; {e(to_wh)}</div>"
        f"<div style='text-align:center;font-size:9pt;line-height:1.3;'>Date: {e(date_str)}</div>"
    )

    col_header = f"<tr><td style='{HL}'>Item</td><td style='{HR}'>Qty</td></tr>"

    items_html = ""
    for line in lines:
        name = line.get("name", "")
        qty  = f"{float(line.get('qty', 0)):g}"
        items_html += f"<tr><td style='{L}'>{e(name)}</td><td style='{R}'>{e(qty)}</td></tr>"

    total_row = (
        f"<tr><td style='{HL}'>TOTAL</td>"
        f"<td style='{HR}'>{e(fmt(total))}</td></tr>"
    )

    return (
        f"<html dir='ltr'><head><meta charset='utf-8'></head>"
        f"<body dir='ltr' style='margin:0;padding:0;"
        f"font-family:monospace;font-size:7pt;line-height:1.2;color:#000;'>"
        f"{header}"
        f"<table style='width:100%;table-layout:fixed;border-collapse:collapse;"
        f"font-family:inherit;font-size:inherit;color:#000;'>"
        f"{SEP}{col_header}{SEP}{items_html}{SEP2}{total_row}{SEP2}"
        f"</table></body></html>"
    )


def print_transfer(
    no: str, from_wh: str, to_wh: str, date_str: str,
    lines: list, currency: str = "", parent=None,
) -> None:
    """
    Print a warehouse transfer receipt.
    Priority (same as print_receipt):
      1. ESC/POS printer → direct thermal print
      2. Windows Qt printer → auto-print via Qt
      3. Fallback → Qt print preview dialog
    """
    from PySide6.QtWidgets import QMessageBox

    # ── 1. ESC/POS — check settings only (no live device open) ────────────
    if _is_escpos_configured():
        ok, err = print_transfer_escpos(
            no=no, from_wh=from_wh, to_wh=to_wh,
            date_str=date_str, lines=lines, currency=currency,
        )
        if not ok and parent:
            QMessageBox.warning(parent, "Printer Error", err)
        return

    html = _build_transfer_html(no, from_wh, to_wh, date_str, lines, currency)

    # ── 2. Windows Qt system printer ───────────────────────────────────────
    qt_name = _get_qt_printer_name()
    if qt_name:
        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        printer.setPrinterName(qt_name)
        printer.setFullPage(False)
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        _render_to_printer(html, printer)
        return

    # ── 3. Preview dialog ──────────────────────────────────────────────────
    printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
    printer.setPageSize(QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter))
    printer.setFullPage(True)
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    _try_set_thermal_printer(printer)

    from PySide6.QtPrintSupport import QPrintPreviewDialog
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle("Transfer Preview")
    dlg.paintRequested.connect(lambda p: _render_to_printer(html, p))
    dlg.exec()


def print_transfer_escpos(
    no: str,
    from_wh: str,
    to_wh: str,
    date_str: str,
    lines: list,
    currency: str = "",
) -> tuple[bool, str]:
    """
    Print a warehouse transfer on the configured ESC/POS printer.
    lines: list of dicts with keys: name, qty, total
    Returns (success, error_message).
    """
    p = get_escpos_printer()
    if p is None:
        return False, "No ESC/POS printer configured.\nGo to Settings → Receipt Printer."

    W      = CHARS_PER_LINE
    qty_w  = 5
    name_w = W - qty_w  # 37 chars for name

    try:
        # ── Top margin (avoid printing on the very edge) ───────────────────
        p.text("\n\n")

        # ── Header ────────────────────────────────────────────────────────
        p.set(align="center", bold=True, double_height=True, double_width=False)
        p.text("Warehouse Transfer\n")
        p.set(align="center", bold=True, double_height=False)
        p.text(f"{no}\n")
        p.set(align="center", bold=False)
        p.text(f"{from_wh}  ->  {to_wh}\n")
        p.text(f"Date: {date_str}\n")
        p.text("-" * W + "\n")

        # ── Column header ──────────────────────────────────────────────────
        p.set(bold=True, align="left")
        p.text(_escpos_row("Name", "Qty", name_w, qty_w))
        p.text("-" * W + "\n")
        p.set(bold=False)

        # ── Item rows ─────────────────────────────────────────────────────
        for line in lines:
            name = str(line.get("name", ""))
            qty  = f"{float(line.get('qty', 0)):g}"
            p.text(_escpos_row(name, qty, name_w, qty_w))

        # ── Total ─────────────────────────────────────────────────────────
        p.text("=" * W + "\n")
        total     = sum(float(l.get("total", 0)) for l in lines)
        total_str = f"{total:,.2f}" + (f" {currency}" if currency else "")
        p.set(bold=True, align="right")
        p.text(f"Total: {total_str}\n")

        # ── Feed + cut ────────────────────────────────────────────────────
        p.text("\n\n\n")
        p.cut()

        return True, ""

    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            p.close()
        except Exception:
            pass


def print_receipt_escpos(
        
    
    data: dict,
    payment_method: str = "cash",
    tendered: float = 0.0,
) -> tuple[bool, str]:
    """
    Print a POS sales receipt on the configured ESC/POS printer.
    Two-line item format: name on line 1, qty x price → total on line 2.
    Wider 80mm layout.
    """
    p = get_escpos_printer()
    if p is None:
        return False, "No ESC/POS printer configured."

    W        = CHARS_PER_LINE
    currency = data.get("currency", "LBP")
    is_lbp   = currency == "LBP"

    def fmt(v: float) -> str:
        return f"{v:,.0f} LBP" if is_lbp else f"$ {v:,.2f}"

    def rrow(label: str, value: str) -> str:
        label = str(label or "")
        value = str(value or "")
        vw = len(value)

        # keep at least 1 space between left and right
        lw = max(1, W - vw - 1)

        # trim left text only if needed
        if len(label) > lw:
            label = label[:lw]

        return f"{label:<{lw}} {value}\n"

    def wrap_text(text: str, width: int):
        text = str(text or "")
        if not text:
            return [""]
        lines = []
        while text:
            lines.append(text[:width])
            text = text[width:]
        return lines

    try:
        # top feed
        p.text("\n")

        # force normal body size
        p.set(align="left", bold=False, double_height=False, double_width=False)

        # debug line to confirm this function is printing
        p.set(align="center", bold=False, double_height=False, double_width=False)
        p.text("ESCPOS ACTIVE\n")

        # header
        p.set(align="center", bold=True, double_height=True, double_width=False)
        p.text(f"{data.get('shop_name', 'Shop')}\n")

        p.set(align="center", bold=False, double_height=False, double_width=False)
        if data.get("shop_address"):
            p.text(f"{data['shop_address']}\n")
        if data.get("shop_phone"):
            p.text(f"Tel: {data['shop_phone']}\n")
        if data.get("warehouse") and data.get("warehouse") != data.get("shop_address"):
            p.text(f"{data['warehouse']}\n")

        p.text("-" * W + "\n")

        # meta
        p.set(align="left", bold=False, double_height=False, double_width=False)
        p.text(rrow("Receipt #:", data.get("invoice_number", "")))
        p.text(rrow("Date:", data.get("sale_datetime") or data.get("date", "")))
        p.text(rrow("Cashier:", data.get("cashier", "")))

        if data.get("customer"):
            customer_lines = wrap_text(str(data["customer"]), W - len("Customer: ") - 1)
            if customer_lines:
                p.text(rrow("Customer:", customer_lines[0]))
                for extra in customer_lines[1:]:
                    p.text(f"{extra}\n")

        p.text("-" * W + "\n")

        # items
        for li in data.get("lines", []):
            desc  = str(li.get("description", ""))
            qty   = li.get("qty", 0)
            price = li.get("unit_price", 0.0)
            total = li.get("total", 0.0)
            disc  = li.get("disc_pct", 0.0)

            # item name wraps
            for line in wrap_text(desc, W):
                p.text(f"{line}\n")

            qty_str  = f"{qty:g}"
            disc_tag = f" (-{disc:.0f}%)" if disc else ""
            detail   = f"  {qty_str} x {fmt(price)}{disc_tag}"

            p.text(rrow(detail, fmt(total)))

        # totals
        p.text("-" * W + "\n")
        p.set(align="left", bold=False, double_height=False, double_width=False)
        p.text(rrow("Subtotal:", fmt(data.get("subtotal", 0.0))))

        if data.get("discount", 0.0):
            p.text(rrow("Discount:", f"-{fmt(data['discount'])}"))

        if data.get("vat", 0.0):
            p.text(rrow("VAT (11%):", fmt(data.get("vat", 0.0))))

        p.text("=" * W + "\n")

        p.set(align="left", bold=True, double_height=False, double_width=False)
        p.text(rrow("TOTAL:", fmt(data.get("total", 0.0))))
        p.set(align="left", bold=False, double_height=False, double_width=False)
        p.text(rrow("Lines:", str(len(data.get("lines", [])))))

        method_label = {"cash": "Cash", "card": "Card", "account": "Account"}.get(
            payment_method, payment_method.capitalize()
        )
        p.text(rrow(f"Paid ({method_label}):", fmt(data.get("amount_paid", 0.0))))

        change = max(0.0, tendered - data.get("total", 0.0)) if payment_method == "cash" else 0.0
        if change > 0:
            p.set(align="left", bold=True, double_height=False, double_width=False)
            p.text(rrow("Change:", fmt(change)))
            p.set(align="left", bold=False, double_height=False, double_width=False)

        # USD equivalent for LBP invoices
        lbp_rate = int(data.get("lbp_rate") or 0)
        inv_total = data.get("total", 0.0)
        if is_lbp and inv_total and lbp_rate:
            usd_equiv = inv_total / lbp_rate
            p.set(align="left", bold=True, double_height=False, double_width=False)
            p.text(rrow("= USD:", f"$ {usd_equiv:,.2f}"))
            p.set(align="left", bold=False, double_height=False, double_width=False)

        # footer
        p.text("-" * W + "\n")
        footer = data.get("receipt_footer", "Thank you!")
        if footer:
            p.set(align="center", bold=False, double_height=False, double_width=False)
            p.text(f"{footer}\n")

        # final feed and cut
        p.text("\n\n\n\n\n\n")
        p.cut()

        return True, ""

    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            p.close()
        except Exception:
            pass