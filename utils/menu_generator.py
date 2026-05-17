"""
Menu generator — builds a PDF menu from active items/categories using QPrinter.
No extra dependencies beyond PySide6-Addons (already required).
"""
from __future__ import annotations
import datetime
import logging

log = logging.getLogger(__name__)


def _get_lbp_rate() -> int:
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        s = get_session()
        try:
            row = s.get(Setting, "lbp_rate")
            return int(row.value) if row and row.value else 89_500
        finally:
            s.close()
    except Exception:
        return 89_500


def get_shop_name() -> str:
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        s = get_session()
        try:
            row = s.get(Setting, "shop_name")
            return row.value if row and row.value else "TannouryMarket"
        finally:
            s.close()
    except Exception:
        return "TannouryMarket"


def fetch_menu_data() -> list[dict]:
    """
    Returns list of category dicts, each with a list of item dicts.
    Only active categories that have at least one active item.
    Price = individual price first, then retail, in LBP.
    """
    from database.engine import get_session, init_db
    from database.models.items import Item
    from sqlalchemy.orm import joinedload
    init_db()
    session = get_session()
    try:
        lbp_rate = _get_lbp_rate()

        items = (
            session.query(Item)
            .options(joinedload(Item.prices), joinedload(Item.category))
            .filter(Item.is_active == True)
            .order_by(Item.name)
            .all()
        )

        cat_map: dict[str, dict] = {}

        for item in items:
            if item.category and item.category.is_active:
                cat_name = item.category.name
                cat_sort = item.category.sort_order
            else:
                cat_name = "Other"
                cat_sort = 999

            price_lbp = _resolve_price_lbp(item, lbp_rate)

            entry = {
                "name":      item.name,
                "name_ar":   item.name_ar or "",
                "price_lbp": price_lbp,
            }

            if cat_name not in cat_map:
                cat_map[cat_name] = {"name": cat_name, "sort": cat_sort, "items": []}
            cat_map[cat_name]["items"].append(entry)

        return sorted(cat_map.values(), key=lambda c: (c["sort"], c["name"]))
    finally:
        session.close()


def _resolve_price_lbp(item, lbp_rate: int) -> int:
    preferred = None
    fallback  = None
    for p in item.prices:
        if p.price_type == "individual" and p.is_default:
            preferred = p
        elif p.price_type == "retail" and p.is_default and preferred is None:
            fallback = p
    price_obj = preferred or fallback
    if price_obj is None:
        return 0
    if price_obj.currency == "LBP":
        return int(price_obj.amount)
    return int(price_obj.amount * lbp_rate)


def generate_menu_pdf(output_path: str, categories: list[dict], shop_name: str) -> None:
    """
    Render a two-column item catalog to a PDF file using QPrinter + QPainter.
    Runs inside the Qt application (must be called from main thread or with QApplication alive).
    """
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtGui import QPainter, QFont, QColor, QBrush, QPen, QPageSize, QPageLayout
    from PySide6.QtCore import QRectF, Qt, QMarginsF

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(output_path)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)

    painter = QPainter()
    painter.begin(printer)

    page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
    W = page_rect.width()

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_title  = QFont("Arial", 22, QFont.Weight.Bold)
    f_date   = QFont("Arial", 9)
    f_cat    = QFont("Arial", 13, QFont.Weight.Bold)
    f_name   = QFont("Arial", 8, QFont.Weight.Bold)
    f_price  = QFont("Arial", 8)

    BLUE     = QColor("#1a3a5c")
    LBLUE    = QColor("#1a6cb5")
    GRAY     = QColor("#5a7090")
    WHITE    = QColor("#ffffff")
    CATBG    = QColor("#1a3a5c")
    CARDBG   = QColor("#f4f6fa")
    CARDBORD = QColor("#c5ccd6")

    COL  = 2           # columns per row
    PAD  = 12
    COLS_SPACING = 10
    now  = datetime.datetime.now().strftime("%d %b %Y")

    col_w = (W - PAD * 2 - COLS_SPACING * (COL - 1)) / COL
    card_h = 54

    y = 0

    def new_page_if_needed(needed_h):
        nonlocal y
        page_h = page_rect.height()
        if y + needed_h > page_h - PAD:
            printer.newPage()
            y = 0

    # ── Header (first page) ───────────────────────────────────────────────────
    painter.setFont(f_title)
    painter.setPen(BLUE)
    painter.drawText(QRectF(PAD, PAD, W - PAD * 2, 40), Qt.AlignLeft | Qt.AlignVCenter, shop_name)

    painter.setFont(f_date)
    painter.setPen(GRAY)
    painter.drawText(QRectF(PAD, PAD + 34, W - PAD * 2, 20), Qt.AlignLeft, f"Price list — {now}")

    # Divider
    painter.setPen(QPen(LBLUE, 2))
    painter.drawLine(int(PAD), int(PAD + 58), int(W - PAD), int(PAD + 58))

    y = PAD + 68

    # ── Categories + items ────────────────────────────────────────────────────
    for cat in categories:
        if not cat["items"]:
            continue

        # Category header
        new_page_if_needed(28 + card_h + 4)
        cat_rect = QRectF(PAD, y, W - PAD * 2, 24)
        painter.setBrush(QBrush(CATBG))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(cat_rect, 4, 4)
        painter.setFont(f_cat)
        painter.setPen(WHITE)
        painter.drawText(cat_rect.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, cat["name"])
        y += 28

        # Items in 2-column grid
        col_idx = 0
        for item in cat["items"]:
            new_page_if_needed(card_h + 4)

            x = PAD + col_idx * (col_w + COLS_SPACING)
            card_rect = QRectF(x, y, col_w, card_h)

            # Card background + border
            painter.setBrush(QBrush(CARDBG))
            painter.setPen(QPen(CARDBORD, 0.5))
            painter.drawRoundedRect(card_rect, 4, 4)

            # Item name
            painter.setFont(f_name)
            painter.setPen(BLUE)
            name_rect = QRectF(x + 6, y + 6, col_w - 12, 28)
            painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, item["name"])

            # Arabic name
            if item["name_ar"]:
                painter.setFont(f_price)
                painter.setPen(GRAY)
                ar_rect = QRectF(x + 6, y + 28, col_w - 12, 14)
                painter.drawText(ar_rect, Qt.AlignRight | Qt.AlignTop, item["name_ar"])

            # Price
            price_txt = f"{item['price_lbp']:,} LBP" if item["price_lbp"] else "—"
            painter.setFont(f_price)
            painter.setPen(LBLUE)
            price_rect = QRectF(x + 6, y + card_h - 18, col_w - 12, 14)
            painter.drawText(price_rect, Qt.AlignLeft | Qt.AlignTop, price_txt)

            col_idx += 1
            if col_idx >= COL:
                col_idx = 0
                y += card_h + 4

        if col_idx != 0:          # flush incomplete row
            y += card_h + 4

        y += 8   # gap between categories

    painter.end()


def generate_qr_png(url: str) -> bytes:
    """Return a QR code PNG as bytes."""
    import qrcode
    from io import BytesIO
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a3a5c", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
