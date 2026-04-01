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
CHARS_PER_LINE = 42   # conservative safe width for 80mm / 203dpi printers


def _build_receipt_text(data: dict, payment_method: str, tendered: float) -> str:
    """Build a plain-text receipt (same layout as ESC/POS) — used for HTML <pre> and Qt print."""
    W        = CHARS_PER_LINE
    currency = data.get("currency", "LBP")
    is_lbp   = currency == "LBP"

    def fmt(v: float) -> str:
        return f"{v:,.0f} L" if is_lbp else f"$ {v:,.2f}"

    def rrow(label: str, value: str) -> str:
        value = str(value)
        vw    = len(value)
        lw    = W - vw
        label = label[:lw]
        return f"{label:<{lw}}{value}"

    rows: list[str] = []

    # Header
    rows.append(data.get("shop_name", "Shop").center(W))
    if data.get("shop_address"):
        rows.append(data["shop_address"].center(W))
    if data.get("shop_phone"):
        rows.append(f"Tel: {data['shop_phone']}".center(W))
    if data.get("warehouse"):
        rows.append(data["warehouse"].center(W))
    rows.append("-" * W)

    # Meta
    rows.append(rrow("Receipt #:", data.get("invoice_number", "")))
    rows.append(rrow("Date:",      data.get("date", "")))
    rows.append(rrow("Cashier:",   data.get("cashier", "")))
    if data.get("customer"):
        rows.append(rrow("Customer:", data["customer"]))
    rows.append("-" * W)

    # Items — two-line format: name then qty x price → total
    for li in data.get("lines", []):
        desc  = str(li.get("description", ""))
        qty   = li.get("qty",        0)
        price = li.get("unit_price", 0.0)
        total = li.get("total",      0.0)
        disc  = li.get("disc_pct",   0.0)

        # Name line (wrap if needed)
        while desc:
            rows.append(desc[:W])
            desc = desc[W:]

        # Detail line: "  qty x price" right-aligned with total
        qty_str  = f"{qty:g}"
        disc_tag = f" (-{disc:.0f}%)" if disc else ""
        detail   = f"  {qty_str} x {fmt(price)}{disc_tag}"
        rows.append(rrow(detail, fmt(total)))

    # Totals
    rows.append("-" * W)
    rows.append(rrow("Subtotal:", fmt(data.get("subtotal", 0.0))))
    if data.get("discount", 0.0):
        rows.append(rrow("Discount:", f"-{fmt(data['discount'])}"))
    if data.get("vat", 0.0):
        rows.append(rrow("VAT (11%):", fmt(data.get("vat", 0.0))))
    rows.append("=" * W)
    rows.append(rrow("TOTAL:", fmt(data.get("total", 0.0))))

    method_label = {"cash": "Cash", "card": "Card", "account": "Account"}.get(
        payment_method, payment_method.capitalize()
    )
    rows.append(rrow(f"Paid ({method_label}):", fmt(data.get("amount_paid", 0.0))))

    change = max(0.0, tendered - data.get("total", 0.0)) if payment_method == "cash" else 0.0
    if change > 0:
        rows.append(rrow("Change:", fmt(change)))

    # Footer
    rows.append("-" * W)
    footer = data.get("receipt_footer", "Thank you!")
    if footer:
        rows.append(footer.center(W))

    return "\n".join(rows)


def _build_html(data: dict, payment_method: str, tendered: float) -> str:
    """Wrap plain-text receipt in <pre> so columns align on any printer/screen."""
    text = _build_receipt_text(data, payment_method, tendered)
    # Escape HTML special characters so <> & in item names don't break layout
    import html as _html
    safe = _html.escape(text)
    return (
        "<html><head><meta charset='utf-8'></head>"
        "<body style='margin:0;padding:0;'>"
        "<pre style=\"font-family:'Courier New',Courier,monospace;"
        "font-size:8pt;margin:0;padding:0;white-space:pre;\">"
        f"{safe}"
        "</pre></body></html>"
    )


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
        html = _build_html(data, payment_method, tendered)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPrinterName(qt_name)
        printer.setPageSize(QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter))
        printer.setPageMargins(QMarginsF(1.0, 2.0, 1.0, 2.0), QPageLayout.Unit.Millimeter)
        printer.setFullPage(False)
        _render_to_printer(html, printer)
        return

    # ── 3. No printer configured — show Qt preview dialog ──────────────────
    html = _build_html(data, payment_method, tendered)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(1.0, 2.0, 1.0, 2.0), QPageLayout.Unit.Millimeter)
    printer.setFullPage(False)
    _try_set_thermal_printer(printer)

    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle("Receipt Preview")
    dlg.paintRequested.connect(lambda p: _render_to_printer(html, p))
    dlg.exec()


def _render_to_printer(html: str, printer: QPrinter) -> None:
    doc = QTextDocument()
    doc.setDocumentMargin(0)          # kill QTextDocument's default 4pt internal indent
    doc.setDefaultStyleSheet("body { margin:0; padding:0; }")
    page_rect = printer.pageRect(QPrinter.Unit.Point)
    doc.setTextWidth(page_rect.width())
    doc.setHtml(html)
    doc.print_(printer)


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
    This handles long item names and large LBP numbers without overflow.
    """
    p = get_escpos_printer()
    if p is None:
        return False, "No ESC/POS printer configured."

    W        = CHARS_PER_LINE   # 42
    currency = data.get("currency", "LBP")
    is_lbp   = currency == "LBP"

    def fmt(v: float) -> str:
        return f"{v:,.0f} L" if is_lbp else f"$ {v:,.2f}"

    # ── helper: right-align a value; same style as _escpos_row ────────────
    def rrow(label: str, value: str) -> str:
        value = str(value)
        vw    = len(value)
        lw    = W - vw
        label = label[:lw]
        return f"{label:<{lw}}{value}\n"

    try:
        # ── Top margin ────────────────────────────────────────────────────
        p.text("\n\n")

        # ── Shop header ───────────────────────────────────────────────────
        p.set(align="center", bold=True, double_height=True, double_width=False)
        p.text(f"{data.get('shop_name', 'Shop')}\n")
        p.set(align="center", bold=False, double_height=False)
        if data.get("shop_address"):
            p.text(f"{data['shop_address']}\n")
        if data.get("shop_phone"):
            p.text(f"Tel: {data['shop_phone']}\n")
        if data.get("warehouse"):
            p.text(f"{data['warehouse']}\n")
        p.text("-" * W + "\n")

        # ── Meta ──────────────────────────────────────────────────────────
        p.set(align="left", bold=False)
        p.text(rrow("Receipt #:", data.get("invoice_number", "")))
        p.text(rrow("Date:",      data.get("date", "")))
        p.text(rrow("Cashier:",   data.get("cashier", "")))
        if data.get("customer"):
            p.text(rrow("Customer:", data["customer"]))
        p.text("-" * W + "\n")

        # ── Item rows ─────────────────────────────────────────────────────
        # Line 1: full item name  (wraps if >W chars, same as transfer)
        # Line 2: "  qty x unit_price"  right-aligned with line total
        for li in data.get("lines", []):
            desc  = str(li.get("description", ""))
            qty   = li.get("qty",        0)
            price = li.get("unit_price", 0.0)
            total = li.get("total",      0.0)
            disc  = li.get("disc_pct",   0.0)

            # Name line — wrap long names (same helper as transfer)
            name_w = W
            if len(desc) <= name_w:
                p.text(f"{desc}\n")
            else:
                while desc:
                    p.text(f"{desc[:name_w]}\n")
                    desc = desc[name_w:]

            # Detail line: "  qty x price" right-aligned with total
            qty_str  = f"{qty:g}"
            disc_tag = f" (-{disc:.0f}%)" if disc else ""
            detail   = f"  {qty_str} x {fmt(price)}{disc_tag}"
            p.text(rrow(detail, fmt(total)))

        # ── Totals ────────────────────────────────────────────────────────
        p.text("-" * W + "\n")
        p.set(bold=False)
        p.text(rrow("Subtotal:", fmt(data.get("subtotal", 0.0))))
        if data.get("discount", 0.0):
            p.text(rrow("Discount:", f"-{fmt(data['discount'])}"))
        if data.get("vat", 0.0):
            p.text(rrow("VAT (11%):", fmt(data.get("vat", 0.0))))
        p.text("=" * W + "\n")
        p.set(bold=True)
        p.text(rrow("TOTAL:", fmt(data.get("total", 0.0))))
        p.set(bold=False)

        method_label = {"cash": "Cash", "card": "Card", "account": "Account"}.get(
            payment_method, payment_method.capitalize()
        )
        p.text(rrow(f"Paid ({method_label}):", fmt(data.get("amount_paid", 0.0))))

        change = max(0.0, tendered - data.get("total", 0.0)) if payment_method == "cash" else 0.0
        if change > 0:
            p.set(bold=True)
            p.text(rrow("Change:", fmt(change)))
            p.set(bold=False)

        # ── Footer ────────────────────────────────────────────────────────
        p.text("-" * W + "\n")
        footer = data.get("receipt_footer", "Thank you!")
        if footer:
            p.set(align="center")
            p.text(f"{footer}\n")

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
