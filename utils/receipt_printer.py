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
