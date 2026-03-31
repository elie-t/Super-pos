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


def _build_html(data: dict, payment_method: str, tendered: float) -> str:
    currency    = data.get("currency", "LBP")
    is_lbp      = currency == "LBP"
    cur_symbol  = "LBP" if is_lbp else "USD"

    def fmt(v: float) -> str:
        if is_lbp:
            return f"{v:,.0f} {cur_symbol}"
        return f"$ {v:,.2f}"

    shop_name    = data.get("shop_name",      "My Supermarket")
    shop_address = data.get("shop_address",   "")
    shop_phone   = data.get("shop_phone",     "")
    footer_text  = data.get("receipt_footer", "Thank you!")
    inv_no       = data.get("invoice_number", "")
    date_str     = data.get("date",           "")
    cashier      = data.get("cashier",        "")
    customer     = data.get("customer",       "")
    warehouse    = data.get("warehouse",      "")

    subtotal    = data.get("subtotal",    0.0)
    discount    = data.get("discount",    0.0)
    vat         = data.get("vat",         0.0)
    total       = data.get("total",       0.0)
    amount_paid = data.get("amount_paid", 0.0)
    change      = max(0.0, tendered - total) if payment_method == "cash" else 0.0

    method_label = {"cash": "Cash", "card": "Card", "account": "Account"}.get(
        payment_method, payment_method.capitalize()
    )

    # ── Header info lines ─────────────────────────────────────────────────────
    address_lines = ""
    if shop_address:
        address_lines += f"<div>{shop_address}</div>"
    if shop_phone:
        address_lines += f"<div>Tel: {shop_phone}</div>"
    if warehouse:
        address_lines += f"<div>{warehouse}</div>"

    # ── Line items ────────────────────────────────────────────────────────────
    lines_html = ""
    for li in data.get("lines", []):
        desc     = li.get("description", "")
        qty      = li.get("qty",        0)
        price    = li.get("unit_price", 0.0)
        disc     = li.get("disc_pct",   0.0)
        line_tot = li.get("total",      0.0)
        qty_str  = f"{qty:g}"
        disc_str = f"<br><small style='color:#888;'>(-{disc:.0f}%)</small>" if disc else ""
        lines_html += f"""
        <tr>
          <td style='padding:2px 2px 2px 0; word-break:break-word;'>{desc}{disc_str}</td>
          <td style='text-align:center; padding:2px; white-space:nowrap;'>{qty_str}</td>
          <td style='text-align:right;  padding:2px; white-space:nowrap;'>{fmt(price)}</td>
          <td style='text-align:right;  padding:2px 0 2px 4px; white-space:nowrap;'><b>{fmt(line_tot)}</b></td>
        </tr>"""

    # ── Optional rows ─────────────────────────────────────────────────────────
    discount_html = ""
    if discount > 0:
        discount_html = f"""
        <tr>
          <td colspan='2'>Discount:</td>
          <td colspan='2' style='text-align:right; color:#c62828;'>- {fmt(discount)}</td>
        </tr>"""

    change_html = ""
    if change > 0:
        change_html = f"""
        <tr>
          <td colspan='2'>Change:</td>
          <td colspan='2' style='text-align:right; color:#2e7d32; font-weight:700;'>{fmt(change)}</td>
        </tr>"""

    html = f"""
<html>
<head>
<meta charset='utf-8'>
</head>
<body style='
    font-family: Arial, Helvetica, sans-serif;
    font-size: 9pt;
    margin: 0;
    padding: 0;
'>

<!-- HEADER -->
<div style='text-align:center; margin-bottom:6px;'>
  <div style='font-size:14pt; font-weight:700;'>{shop_name}</div>
  <div style='font-size:9pt;'>{address_lines}</div>
</div>

<hr style='border:none; border-top:1px dashed #000; margin:4px 0;'>

<!-- META -->
<table style='width:100%; font-size:9pt; border-collapse:collapse;'>
  <tr><td style='padding:1px 0;'><b>Receipt #:</b></td>
      <td style='text-align:right; padding:1px 0;'>{inv_no}</td></tr>
  <tr><td style='padding:1px 0;'><b>Date:</b></td>
      <td style='text-align:right; padding:1px 0;'>{date_str}</td></tr>
  <tr><td style='padding:1px 0;'><b>Cashier:</b></td>
      <td style='text-align:right; padding:1px 0;'>{cashier}</td></tr>
  <tr><td style='padding:1px 0;'><b>Customer:</b></td>
      <td style='text-align:right; padding:1px 0;'>{customer}</td></tr>
</table>

<hr style='border:none; border-top:1px dashed #000; margin:4px 0;'>

<!-- ITEMS TABLE — col widths: item=50% qty=8% price=21% total=21% -->
<table style='width:100%; font-size:9pt; border-collapse:collapse;'>
  <colgroup>
    <col style='width:50%;'>
    <col style='width:8%;'>
    <col style='width:21%;'>
    <col style='width:21%;'>
  </colgroup>
  <thead>
    <tr style='border-bottom:1px solid #000;'>
      <th style='text-align:left;   padding-bottom:3px;'>Item</th>
      <th style='text-align:center; padding-bottom:3px;'>Qty</th>
      <th style='text-align:right;  padding-bottom:3px;'>Price</th>
      <th style='text-align:right;  padding-bottom:3px;'>Total</th>
    </tr>
  </thead>
  <tbody>
    {lines_html}
  </tbody>
</table>

<hr style='border:none; border-top:1px dashed #000; margin:4px 0;'>

<!-- TOTALS -->
<table style='width:100%; font-size:9pt; border-collapse:collapse;'>
  <tr>
    <td colspan='2' style='padding:2px 0;'>Subtotal:</td>
    <td colspan='2' style='text-align:right; padding:2px 0; white-space:nowrap;'>{fmt(subtotal)}</td>
  </tr>
  {discount_html}
  <tr>
    <td colspan='2' style='padding:2px 0;'>VAT (11%):</td>
    <td colspan='2' style='text-align:right; padding:2px 0; white-space:nowrap;'>{fmt(vat)}</td>
  </tr>
  <tr style='font-size:11pt; font-weight:700; border-top:1px solid #000;'>
    <td colspan='2' style='padding:4px 0;'>TOTAL:</td>
    <td colspan='2' style='text-align:right; padding:4px 0; white-space:nowrap;'>{fmt(total)}</td>
  </tr>
  <tr>
    <td colspan='2' style='padding:2px 0;'>Paid ({method_label}):</td>
    <td colspan='2' style='text-align:right; padding:2px 0; white-space:nowrap;'>{fmt(amount_paid)}</td>
  </tr>
  {change_html}
</table>

<hr style='border:none; border-top:1px dashed #000; margin:6px 0;'>

<!-- FOOTER -->
<div style='text-align:center; font-size:9pt;'>{footer_text}</div>

</body>
</html>
"""
    return html


def print_receipt(
    data: dict,
    payment_method: str = "cash",
    tendered: float = 0.0,
    parent=None,
    show_preview: bool = True,
) -> None:
    # ── Try ESC/POS direct print first ────────────────────────────────────
    try:
        if get_escpos_printer() is not None:
            ok, err = print_receipt_escpos(data, payment_method, tendered)
            if not ok and parent:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Printer Error", err)
            return
    except Exception:
        pass  # fall through to Qt preview

    html = _build_html(data, payment_method, tendered)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageSize(QPageSize(QSizeF(80, 297), QPageSize.Unit.Millimeter))
    printer.setPageMargins(QMarginsF(3.0, 3.0, 3.0, 3.0), QPageLayout.Unit.Millimeter)
    printer.setFullPage(False)

    _try_set_thermal_printer(printer)

    if show_preview:
        dlg = QPrintPreviewDialog(printer, parent)
        dlg.setWindowTitle("Receipt Preview")
        dlg.paintRequested.connect(lambda p: _render_to_printer(html, p))
        dlg.exec()
    else:
        if QPrinterInfo.defaultPrinter().isNull():
            dlg = QPrintPreviewDialog(printer, parent)
            dlg.setWindowTitle("Receipt Preview — No default printer")
            dlg.paintRequested.connect(lambda p: _render_to_printer(html, p))
            dlg.exec()
        else:
            _render_to_printer(html, printer)


def _render_to_printer(html: str, printer: QPrinter) -> None:
    doc = QTextDocument()
    doc.setDefaultStyleSheet("body { margin:0; padding:0; }")
    # Use logical (point-based) width so it's DPI-independent
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
# 80 mm paper → 72 mm printable → 576 dots @ 203 dpi → 48 chars (Font A 12-dot)

CHARS_PER_LINE = 42   # conservative safe width for 80mm / 203dpi printers


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
    Mirrors the layout of _build_html() but in ESC/POS commands.
    """
    p = get_escpos_printer()
    if p is None:
        return False, "No ESC/POS printer configured."

    W       = CHARS_PER_LINE
    currency = data.get("currency", "LBP")
    is_lbp  = currency == "LBP"

    def fmt(v: float) -> str:
        return f"{v:,.0f} L" if is_lbp else f"$ {v:,.2f}"

    # column widths: desc=28 qty=4 price=8 total=8
    dw, qw, pw, tw = 28, 4, 8, 8

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
        p.text(_escpos_row("Receipt #:", data.get("invoice_number", ""), W - 16, 16))
        p.text(_escpos_row("Date:",      data.get("date", ""),            W - 16, 16))
        p.text(_escpos_row("Cashier:",   data.get("cashier", ""),         W - 16, 16))
        if data.get("customer"):
            p.text(_escpos_row("Customer:", data["customer"],             W - 16, 16))
        p.text("-" * W + "\n")

        # ── Items header ──────────────────────────────────────────────────
        p.set(bold=True)
        p.text(f"{'Item':<{dw}}{'Qty':>{qw}}{'Price':>{pw}}{'Total':>{tw}}\n")
        p.text("-" * W + "\n")
        p.set(bold=False)

        # ── Item rows ─────────────────────────────────────────────────────
        for li in data.get("lines", []):
            desc  = str(li.get("description", ""))
            qty   = f"{li.get('qty', 0):g}"
            price = fmt(li.get("unit_price", 0))
            total = fmt(li.get("total", 0))
            disc  = li.get("disc_pct", 0)

            # Truncate/wrap description
            if len(desc) <= dw:
                p.text(f"{desc:<{dw}}{qty:>{qw}}{price:>{pw}}{total:>{tw}}\n")
            else:
                p.text(f"{desc[:dw]}{qty:>{qw}}{price:>{pw}}{total:>{tw}}\n")
                rest = desc[dw:]
                while rest:
                    p.text(f"  {rest[:W - 2]}\n")
                    rest = rest[W - 2:]
            if disc:
                p.text(f"  (-{disc:.0f}%)\n")

        # ── Totals ────────────────────────────────────────────────────────
        p.text("-" * W + "\n")
        p.set(bold=False)
        p.text(_escpos_row("Subtotal:", fmt(data.get("subtotal", 0)), W - 12, 12))
        if data.get("discount", 0):
            p.text(_escpos_row("Discount:", f"-{fmt(data['discount'])}", W - 12, 12))
        if data.get("vat", 0):
            p.text(_escpos_row("VAT (11%):", fmt(data.get("vat", 0)), W - 12, 12))
        p.text("=" * W + "\n")
        p.set(bold=True)
        p.text(_escpos_row("TOTAL:", fmt(data.get("total", 0)), W - 12, 12))
        p.set(bold=False)

        method_label = {"cash": "Cash", "card": "Card", "account": "Account"}.get(
            payment_method, payment_method.capitalize()
        )
        p.text(_escpos_row(f"Paid ({method_label}):", fmt(data.get("amount_paid", 0)), W - 12, 12))

        change = max(0.0, tendered - data.get("total", 0)) if payment_method == "cash" else 0.0
        if change > 0:
            p.set(bold=True)
            p.text(_escpos_row("Change:", fmt(change), W - 12, 12))
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
