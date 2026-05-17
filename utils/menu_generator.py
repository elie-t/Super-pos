"""
Menu generator — builds a self-contained HTML menu from active items/categories.
Prices shown in LBP using the individual (POS) price type.
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


def _get_shop_name() -> str:
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
    Returns list of category dicts:
      [{"name": str, "items": [{"name": str, "name_ar": str, "price_lbp": int, "photo_url": str|None}]}]
    Only active categories with at least one active item.
    Price = individual first, then retail, then 0.
    """
    from database.engine import get_session, init_db
    from database.models.items import Item, Category, ItemPrice
    from sqlalchemy.orm import joinedload
    init_db()
    session = get_session()
    try:
        lbp_rate = _get_lbp_rate()

        items = (
            session.query(Item)
            .options(
                joinedload(Item.prices),
                joinedload(Item.category),
            )
            .filter(Item.is_active == True)
            .order_by(Item.name)
            .all()
        )

        cat_map: dict[str, dict] = {}   # cat_name → {name, sort, items}

        for item in items:
            cat_name = item.category.name if item.category and item.category.is_active else "Other"
            cat_sort = item.category.sort_order if item.category else 999

            # Resolve price in LBP
            price_lbp = _resolve_price_lbp(item, lbp_rate)

            entry = {
                "name":      item.name,
                "name_ar":   item.name_ar or "",
                "price_lbp": price_lbp,
                "photo_url": item.photo_url or "",
            }

            if cat_name not in cat_map:
                cat_map[cat_name] = {"name": cat_name, "sort": cat_sort, "items": []}
            cat_map[cat_name]["items"].append(entry)

        result = sorted(cat_map.values(), key=lambda c: (c["sort"], c["name"]))
        return result
    finally:
        session.close()


def _resolve_price_lbp(item, lbp_rate: int) -> int:
    """Pick individual → retail price and convert to LBP."""
    preferred = None
    fallback = None
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
    else:
        return int(price_obj.amount * lbp_rate)


def build_menu_html(categories: list[dict], shop_name: str) -> str:
    """Render the full self-contained HTML menu string."""
    now = datetime.datetime.now().strftime("%d %b %Y")
    cat_tabs  = _build_tabs(categories)
    cat_cards = _build_cards(categories)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{shop_name} — Menu</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f4f6fa;color:#1a3a5c;}}
  header{{background:linear-gradient(135deg,#1a3a5c,#1a6cb5);color:#fff;padding:18px 20px 14px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.25)}}
  header h1{{font-size:1.4rem;font-weight:800;letter-spacing:.5px}}
  header p{{font-size:.75rem;opacity:.75;margin-top:2px}}
  .tabs{{display:flex;gap:8px;overflow-x:auto;padding:12px 16px 0;background:#fff;border-bottom:2px solid #e0e8f5;position:sticky;top:66px;z-index:90;scrollbar-width:none}}
  .tabs::-webkit-scrollbar{{display:none}}
  .tab{{white-space:nowrap;padding:8px 16px;border-radius:20px 20px 0 0;border:1px solid #c5d8f0;border-bottom:none;cursor:pointer;font-size:.8rem;font-weight:600;color:#5a7090;background:#f4f6fa;transition:all .2s}}
  .tab.active,.tab:hover{{background:#1a3a5c;color:#fff;border-color:#1a3a5c}}
  .section{{display:none;padding:16px}}
  .section.active{{display:block}}
  .section-title{{font-size:1.1rem;font-weight:800;color:#1a3a5c;margin-bottom:14px;padding-bottom:6px;border-bottom:2px solid #1a6cb5}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px}}
  .card{{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08);transition:transform .15s}}
  .card:hover{{transform:translateY(-2px)}}
  .card img{{width:100%;height:110px;object-fit:cover;background:#e8f0fb}}
  .card-no-img{{width:100%;height:80px;background:linear-gradient(135deg,#e8f0fb,#d0e4f7);display:flex;align-items:center;justify-content:center;font-size:2rem}}
  .card-body{{padding:10px}}
  .card-name{{font-size:.82rem;font-weight:700;color:#1a3a5c;line-height:1.3;margin-bottom:2px}}
  .card-name-ar{{font-size:.77rem;color:#5a7090;direction:rtl;margin-bottom:6px}}
  .card-price{{font-size:.9rem;font-weight:800;color:#1a6cb5}}
  .card-price span{{font-size:.7rem;font-weight:500;color:#7a90a8}}
  footer{{text-align:center;padding:24px;color:#9aabbf;font-size:.72rem}}
</style>
</head>
<body>
<header>
  <h1>🛒 {shop_name}</h1>
  <p>Updated {now}</p>
</header>
<div class="tabs" id="tabs">
{cat_tabs}
</div>
<div id="sections">
{cat_cards}
</div>
<footer>{shop_name} · Prices in LBP · {now}</footer>
<script>
var tabs=document.querySelectorAll('.tab');
var secs=document.querySelectorAll('.section');
tabs.forEach(function(t,i){{
  t.addEventListener('click',function(){{
    tabs.forEach(function(x){{x.classList.remove('active')}});
    secs.forEach(function(x){{x.classList.remove('active')}});
    t.classList.add('active');
    secs[i].classList.add('active');
  }});
}});
</script>
</body>
</html>"""


def _build_tabs(categories: list[dict]) -> str:
    lines = []
    for i, cat in enumerate(categories):
        active = " active" if i == 0 else ""
        lines.append(f'  <div class="tab{active}">{cat["name"]}</div>')
    return "\n".join(lines)


def _build_cards(categories: list[dict]) -> str:
    lines = []
    for i, cat in enumerate(categories):
        active = " active" if i == 0 else ""
        lines.append(f'<div class="section{active}">')
        lines.append(f'  <div class="section-title">{cat["name"]}</div>')
        lines.append('  <div class="grid">')
        for item in cat["items"]:
            lines.append(_item_card(item))
        lines.append("  </div>")
        lines.append("</div>")
    return "\n".join(lines)


def _item_card(item: dict) -> str:
    name     = item["name"].replace("&", "&amp;").replace("<", "&lt;")
    name_ar  = item["name_ar"].replace("&", "&amp;").replace("<", "&lt;")
    price    = f"{item['price_lbp']:,}" if item["price_lbp"] else "—"
    ar_line  = f'<div class="card-name-ar">{name_ar}</div>' if name_ar else ""

    if item["photo_url"]:
        img = f'<img src="{item["photo_url"]}" alt="{name}" loading="lazy">'
    else:
        icon = _category_icon(item["name"])
        img  = f'<div class="card-no-img">{icon}</div>'

    return f"""    <div class="card">
      {img}
      <div class="card-body">
        <div class="card-name">{name}</div>
        {ar_line}
        <div class="card-price">{price} <span>LBP</span></div>
      </div>
    </div>"""


def _category_icon(name: str) -> str:
    n = name.lower()
    if any(w in n for w in ("drink", "juice", "water", "soda", "cola", "pepsi")):  return "🥤"
    if any(w in n for w in ("bread", "pita", "kaak")):                              return "🥖"
    if any(w in n for w in ("meat", "chicken", "beef", "lamb")):                    return "🥩"
    if any(w in n for w in ("dairy", "milk", "cheese", "yogurt", "laban")):         return "🥛"
    if any(w in n for w in ("sweet", "candy", "chocolate", "snack", "chips")):      return "🍫"
    if any(w in n for w in ("fruit", "apple", "banana", "orange")):                 return "🍎"
    if any(w in n for w in ("vegetable", "veggie", "salad")):                       return "🥦"
    if any(w in n for w in ("coffee", "tea", "nescafe")):                           return "☕"
    if any(w in n for w in ("oil", "olive")):                                       return "🫙"
    if any(w in n for w in ("clean", "soap", "deterg", "hygiene")):                 return "🧴"
    return "📦"


def generate_qr_png(url: str) -> bytes:
    """Return a QR code PNG as bytes pointing to the given URL."""
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
