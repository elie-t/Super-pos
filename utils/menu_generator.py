"""
Menu generator — classic single-page HTML menu, two-column restaurant style.
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
            entry = {
                "name":      item.name,
                "name_ar":   item.name_ar or "",
                "price_lbp": _resolve_price_lbp(item, lbp_rate),
            }
            if cat_name not in cat_map:
                cat_map[cat_name] = {"name": cat_name, "sort": cat_sort, "items": []}
            cat_map[cat_name]["items"].append(entry)
        return sorted(cat_map.values(), key=lambda c: (c["sort"], c["name"]))
    finally:
        session.close()


def _resolve_price_lbp(item, lbp_rate: int) -> int:
    preferred = fallback = None
    for p in item.prices:
        if p.price_type == "individual" and p.is_default:
            preferred = p
        elif p.price_type == "retail" and p.is_default and preferred is None:
            fallback = p
    price_obj = preferred or fallback
    if price_obj is None:
        return 0
    return int(price_obj.amount) if price_obj.currency == "LBP" else int(price_obj.amount * lbp_rate)


def build_menu_html(categories: list[dict], shop_name: str) -> str:
    now      = datetime.datetime.now().strftime("%d %b %Y")
    sections = "".join(_cat_section(cat) for cat in categories)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(shop_name)}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=Lato:wght@400;700&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: #f7f3ed;
    color: #1a2a3a;
    font-family: 'Lato', 'Segoe UI', sans-serif;
    min-height: 100vh;
  }}

  /* ── Header ── */
  header {{
    text-align: center;
    padding: 44px 20px 28px;
    border-bottom: 1px solid #ccc;
    background: #fff;
  }}
  .shop-name {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: clamp(2rem, 6vw, 3.2rem);
    font-weight: 900;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: #1a3a5c;
  }}
  .shop-sub {{
    font-size: .8rem;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #7a8898;
    margin-top: 6px;
  }}
  .shop-date {{
    font-size: .72rem;
    color: #aaa;
    margin-top: 10px;
  }}

  /* ── Divider ornament ── */
  .ornament {{
    text-align: center;
    color: #1a3a5c;
    font-size: 1.2rem;
    letter-spacing: 10px;
    margin: 18px 0 0;
  }}

  /* ── Two-column layout ── */
  .menu-columns {{
    column-count: 2;
    column-gap: 0;
    padding: 0;
  }}
  @media (max-width: 640px) {{
    .menu-columns {{ column-count: 1; }}
  }}

  /* ── Category block ── */
  .category {{
    break-inside: avoid;
    padding: 28px 36px 20px;
    border-bottom: 1px solid #e0d8ce;
  }}
  .category:nth-child(odd)  {{ border-right: 1px solid #e0d8ce; }}
  @media (max-width: 640px) {{
    .category:nth-child(odd) {{ border-right: none; }}
  }}

  .cat-title {{
    font-family: 'Playfair Display', Georgia, serif;
    font-size: clamp(1.3rem, 3.5vw, 1.8rem);
    font-weight: 900;
    color: #1a3a5c;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid #1a3a5c;
  }}

  /* ── Item row ── */
  .item {{
    display: flex;
    align-items: baseline;
    gap: 6px;
    margin-bottom: 10px;
  }}
  .item-left {{
    flex: 1;
    min-width: 0;
  }}
  .item-name {{
    font-size: .85rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .6px;
    color: #1a2a3a;
    line-height: 1.3;
  }}
  .item-ar {{
    font-size: .78rem;
    color: #7a8898;
    direction: rtl;
    font-style: italic;
    margin-top: 1px;
  }}
  .dots {{
    flex: 1;
    min-width: 16px;
    border-bottom: 1px dotted #aab0ba;
    margin-bottom: 4px;
  }}
  .item-price {{
    font-size: .85rem;
    font-weight: 700;
    color: #1a3a5c;
    white-space: nowrap;
  }}
  .currency {{
    font-size: .68rem;
    font-weight: 400;
    color: #7a8898;
    margin-left: 2px;
  }}

  /* ── Footer ── */
  footer {{
    text-align: center;
    padding: 22px 16px;
    font-size: .72rem;
    color: #aaa;
    border-top: 1px solid #e0d8ce;
    background: #fff;
  }}
</style>
</head>
<body>

<header>
  <div class="shop-name">{_esc(shop_name)}</div>
  <div class="shop-sub">Price List</div>
  <div class="ornament">✦ ✦ ✦</div>
  <div class="shop-date">Updated {now}</div>
</header>

<div class="menu-columns">
{sections}
</div>

<footer>{_esc(shop_name)} &nbsp;·&nbsp; All prices in LBP &nbsp;·&nbsp; {now}</footer>

</body>
</html>"""


def _cat_section(cat: dict) -> str:
    items_html = "".join(_item_row(it) for it in cat["items"])
    return (
        f'<div class="category">\n'
        f'  <div class="cat-title">{_esc(cat["name"])}</div>\n'
        f'{items_html}'
        f'</div>\n'
    )


def _item_row(item: dict) -> str:
    price = f"{item['price_lbp']:,}" if item["price_lbp"] else "—"
    ar = (f'<div class="item-ar">{_esc(item["name_ar"])}</div>'
          if item["name_ar"] else "")
    return (
        f'  <div class="item">\n'
        f'    <div class="item-left">'
        f'<div class="item-name">{_esc(item["name"])}</div>{ar}'
        f'</div>\n'
        f'    <div class="dots"></div>\n'
        f'    <div class="item-price">{price}<span class="currency">ل.ل</span></div>\n'
        f'  </div>\n'
    )


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_qr_png(url: str) -> bytes:
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
