"""
Scale barcode decoder.

Supports EAN-13 barcodes emitted by pricing scales (price-embedded or
weight-embedded).  Multiple scale profiles are supported so you can have
different configurations for each physical scale you use.

Barcode structure example (13-digit EAN-13):
  [ flag (F digits) ] [ PLU code (C digits) ] [ payload (P digits) ] [ EAN-check (1 digit) ]
  F + C + P + 1 = 13   (or +2 if the scale embeds its own internal checksum byte)

Example from label:  2702105985005
  flag   = "27"     (2 digits)
  PLU    = "021"    (3 digits)  → item code "27021" (prefix "27" + "021")
  price  = "0598500" (7 digits) → 598 500 LBP  (decimals=0)
  EAN-13 check = "5"

Scale configs are stored as a JSON array in the settings table
under key  'scale_configs'.

Each config object:
  {
    "id":                   "scale1",          # internal unique id
    "name":                 "Scale 1",         # display name
    "enabled":              true,
    "flag_length":          2,                 # digits that identify this scale
    "flag_value":           "27",              # expected flag string
    "code_length":          3,                 # PLU digits after flag
    "payload_length":       7,                 # price / weight digits
    "payload_type":         "price",           # "price" | "weight"
    "payload_decimals":     0,                 # decimal places (0 → whole LBP)
    "has_internal_checksum": false,            # scale adds its own check digit
    "code_prefix":          "27"               # prepended to PLU for DB code lookup
  }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScaleDecodeResult:
    config_name: str
    item_code:   str           # code used for DB lookup  (prefix + PLU)
    price:       Optional[float]   # embedded price when payload_type=="price"
    weight:      Optional[float]   # embedded weight when payload_type=="weight"
    raw_code:    str           # extracted PLU digits only
    raw_payload: str           # extracted payload digits only


# ── Config I/O ────────────────────────────────────────────────────────────────

def load_scale_configs() -> list[dict]:
    """Return scale config list from the settings table (or [] on error)."""
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            s = session.get(Setting, "scale_configs")
            if s and s.value:
                return json.loads(s.value)
        finally:
            session.close()
    except Exception:
        pass
    return []


def save_scale_configs(configs: list[dict]) -> None:
    """Persist scale config list to the settings table."""
    from database.engine import get_session, init_db
    from database.models.items import Setting
    init_db()
    session = get_session()
    try:
        payload = json.dumps(configs, ensure_ascii=False)
        s = session.get(Setting, "scale_configs")
        if s:
            s.value = payload
        else:
            session.add(Setting(key="scale_configs", value=payload,
                                description="Scale barcode configurations"))
        session.commit()
    finally:
        session.close()


# ── Decoder ───────────────────────────────────────────────────────────────────

def decode_scale_barcode(barcode: str) -> Optional[ScaleDecodeResult]:
    """
    Try to decode *barcode* using any enabled scale config.
    Returns a ScaleDecodeResult on match, None otherwise.
    """
    bc = barcode.strip()
    if not bc.isdigit():
        return None

    for cfg in load_scale_configs():
        if not cfg.get("enabled", True):
            continue

        flag_len  = int(cfg.get("flag_length",  2))
        flag_val  = str(cfg.get("flag_value",  "27"))
        code_len  = int(cfg.get("code_length",  3))
        pay_len   = int(cfg.get("payload_length", 7))
        has_chk   = bool(cfg.get("has_internal_checksum", False))
        pay_type  = cfg.get("payload_type", "price")
        pay_dec   = int(cfg.get("payload_decimals", 0))
        code_pfx  = str(cfg.get("code_prefix", flag_val))

        # Expected total length: flag + PLU + payload + [internal_chk] + EAN_check(1)
        # Some scanners strip the EAN-13 check digit → accept both lengths
        base     = flag_len + code_len + pay_len + (1 if has_chk else 0)
        expected = base + 1   # with EAN check digit
        if len(bc) not in (expected, base):
            continue

        # Flag must match
        if bc[:flag_len] != flag_val:
            continue

        # Slice out parts
        pos      = flag_len
        raw_code = bc[pos: pos + code_len];  pos += code_len
        raw_pay  = bc[pos: pos + pay_len]

        # Parse embedded numeric value
        try:
            raw_int = int(raw_pay)
            value   = raw_int / (10 ** pay_dec) if pay_dec > 0 else float(raw_int)
        except ValueError:
            continue

        return ScaleDecodeResult(
            config_name = cfg.get("name", "Scale"),
            item_code   = code_pfx + raw_code,
            price       = value if pay_type == "price"  else None,
            weight      = value if pay_type == "weight" else None,
            raw_code    = raw_code,
            raw_payload = raw_pay,
        )

    return None
