"""
Menu generator — builds a self-contained HTML menu from active items/categories.
Saved to OneDrive folder; shared link used to generate the QR code.
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
    Returns sorted list of category dicts, each with a list of item dicts.
    Only active categories with at least one active item.
    Price = individual first, then retail, converted to LBP.
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

            entry = {
                "name":      item.name,
                "name_ar":   item.name_ar or "",
                "price_lbp": _resolve_price_lbp(item, lbp_rate),
                "photo_url": item.photo_url or "",
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
    cat_tabs = _build_tabs(categories)
    cat_body = _build_sections(categories)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(shop_name)} — Menu</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f4f6fa;color:#1a3a5c}}
header{{background:linear-gradient(135deg,#1a3a5c,#1a6cb5);color:#fff;padding:18px 20px 14px;
        position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25)}}
header h1{{font-size:1.5rem;font-weight:800}}
header p{{font-size:.75rem;opacity:.7;margin-top:3px}}
.tabs{{display:flex;gap:6px;overflow-x:auto;padding:10px 14px 0;background:#fff;
       border-bottom:2px solid #e0e8f5;position:sticky;top:63px;z-index:90;scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{white-space:nowrap;padding:8px 18px;border-radius:18px 18px 0 0;
      border:1px solid #c5d8f0;border-bottom:none;cursor:pointer;
      font-size:.82rem;font-weight:700;color:#5a7090;background:#f4f6fa;transition:.2s}}
.tab.active,.tab:hover{{background:#1a3a5c;color:#fff;border-color:#1a3a5c}}
.section{{display:none;padding:16px 14px}}
.section.active{{display:block}}
.section-title{{font-size:1.1rem;font-weight:800;margin-bottom:14px;padding-bottom:8px;
                border-bottom:3px solid #1a6cb5;color:#1a3a5c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}}
.card{{background:#fff;border-radius:10px;overflow:hidden;
       box-shadow:0 1px 5px rgba(0,0,0,.09);transition:transform .15s}}
.card:hover{{transform:translateY(-2px)}}
.card img{{width:100%;height:110px;object-fit:cover}}
.no-img{{width:100%;height:80px;background:linear-gradient(135deg,#e8f0fb,#d0e4f7);
         display:flex;align-items:center;justify-content:center;font-size:2rem}}
.card-body{{padding:10px}}
.card-name{{font-size:.83rem;font-weight:700;color:#1a3a5c;line-height:1.3;margin-bottom:2px}}
.card-ar{{font-size:.76rem;color:#5a7090;direction:rtl;margin-bottom:6px}}
.card-price{{font-size:.95rem;font-weight:800;color:#1a6cb5}}
.card-price span{{font-size:.7rem;font-weight:500;color:#7a90a8;margin-left:2px}}
footer{{text-align:center;padding:24px 16px;color:#9aabbf;font-size:.72rem}}
</style>
</head>
<body>
<header>
  <h1>🛒 {_esc(shop_name)}</h1>
  <p>Updated {now}</p>
</header>
<div class="tabs">{cat_tabs}</div>
<div id="sections">{cat_body}</div>
<footer>{_esc(shop_name)} · Prices in LBP · {now}</footer>
<script>
var tabs=document.querySelectorAll('.tab');
var secs=document.querySelectorAll('.section');
tabs.forEach(function(t,i){{
  t.addEventListener('click',function(){{
    tabs.forEach(function(x){{x.classList.remove('active')}});
    secs.forEach(function(x){{x.classList.remove('active')}});
    t.classList.add('active');secs[i].classList.add('active');
  }});
}});
</script>
</body>
</html>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_tabs(categories: list[dict]) -> str:
    return "".join(
        f'<div class="tab{" active" if i == 0 else ""}">{_esc(c["name"])}</div>'
        for i, c in enumerate(categories)
    )


def _build_sections(categories: list[dict]) -> str:
    parts = []
    for i, cat in enumerate(categories):
        active = " active" if i == 0 else ""
        cards  = "".join(_item_card(it) for it in cat["items"])
        parts.append(
            f'<div class="section{active}">'
            f'<div class="section-title">{_esc(cat["name"])}</div>'
            f'<div class="grid">{cards}</div>'
            f'</div>'
        )
    return "".join(parts)


def _item_card(item: dict) -> str:
    price = f"{item['price_lbp']:,}" if item["price_lbp"] else "—"
    ar    = f'<div class="card-ar">{_esc(item["name_ar"])}</div>' if item["name_ar"] else ""
    img   = (f'<img src="{item["photo_url"]}" alt="{_esc(item["name"])}" loading="lazy">'
             if item["photo_url"] else f'<div class="no-img">{_icon(item["name"])}</div>')
    return (
        f'<div class="card">{img}'
        f'<div class="card-body">'
        f'<div class="card-name">{_esc(item["name"])}</div>{ar}'
        f'<div class="card-price">{price}<span>LBP</span></div>'
        f'</div></div>'
    )


def _icon(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ("drink","juice","water","soda","cola","pepsi")): return "🥤"
    if any(w in n for w in ("bread","pita","kaak")):                         return "🥖"
    if any(w in n for w in ("meat","chicken","beef","lamb")):                return "🥩"
    if any(w in n for w in ("dairy","milk","cheese","yogurt","laban")):      return "🥛"
    if any(w in n for w in ("sweet","candy","chocolate","snack","chips")):   return "🍫"
    if any(w in n for w in ("fruit","apple","banana","orange")):             return "🍎"
    if any(w in n for w in ("vegetable","veggie","salad")):                  return "🥦"
    if any(w in n for w in ("coffee","tea","nescafe")):                      return "☕"
    if any(w in n for w in ("oil","olive")):                                 return "🫙"
    if any(w in n for w in ("clean","soap","deterg","hygiene")):             return "🧴"
    return "📦"


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
