"""
USB/Serial Pole Display (Customer Display) — 2-line VFD/LCD
Supports the most common protocols used by built-in POS poles.
"""
from __future__ import annotations
import logging

log = logging.getLogger(__name__)

WIDTH = 20   # characters per line


def _pad(text: str, width: int = WIDTH) -> str:
    return f"{str(text)[:width]:<{width}}"


def _get_port_settings() -> dict:
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            def _g(key, default=""):
                s = session.get(Setting, key)
                return s.value if s else default
            return {
                "port":     _g("pole_port", "") or None,
                "baud":     int(_g("pole_baud",     "9600")  or "9600"),
                "protocol": _g("pole_protocol", "simple"),
                "lines":    int(_g("pole_lines",    "1")     or "1"),
                "databits": int(_g("pole_databits", "8")     or "8"),
                "parity":   _g("pole_parity", "N"),
                "stopbits": float(_g("pole_stopbits", "1")   or "1"),
            }
        finally:
            session.close()
    except Exception:
        return {"port": None, "baud": 9600, "protocol": "simple", "lines": 1,
                "databits": 8, "parity": "N", "stopbits": 1.0}


def _digits_only(text: str, width: int = 8) -> str:
    """Keep only digits from text, right-justify in width chars, zero-pad."""
    digits = "".join(c for c in text if c.isdigit())
    return digits[:width].rjust(width, "0")


def _led8n_format(value_str: str, width: int = 8) -> str:
    """Format a number for 8-digit LED display.

    Right-aligns with leading spaces so unused positions are blank.
        492250  →  "  492250"
        984500  →  "  984500"
       1984500  →  " 1984500"
          5500  →  "    5500"
             0  →  "00000000"   (idle/clear state)
    """
    digits = "".join(c for c in str(value_str) if c.isdigit())
    n = int(digits) if digits else 0
    if n == 0:
        return "0" * width
    s = str(n)
    if len(s) > width:
        s = s[-width:]       # keep rightmost digits if overflow
    return s.rjust(width)    # right-align, space-pad on the left


def _build_packet(line1: str, line2: str, protocol: str, lines: int = 1) -> bytes:
    """Return the byte sequence to display on the pole.
    If lines==1, line2 is ignored and only line1 is sent.

    For 'led8n' protocol (GS-T5 and similar 8-digit numeric LED displays):
      line1 = item price (digits only, e.g. "1500")
      line2 = running total (digits only)
    """

    # ── LED 8N numeric display variants ──────────────────────────────────────
    # Single-row display: only send the value we want to show (line2 = price
    # during item scan, total during payment).  Sending two rows with \r
    # between them bleeds the CR into the display as an extra character.
    if protocol == "led8n":
        # 8 raw bytes, no STX, no CR — display shows exactly what it receives.
        # STX prefix confuses this display (treats STX+next_byte as 2-byte
        # command header, skipping them), and trailing CR renders as '0'.
        val = _led8n_format(line2 if line2 else line1, 8)
        return val.encode("ascii")   # exactly 8 bytes

    if protocol == "led8n_stx":
        val = _led8n_format(line2 if line2 else line1, 8)
        return b"\x02" + val.encode("ascii") + b"\r"

    if protocol == "led8n_16":
        # Some displays: 16 raw digits, display splits at 8 internally
        p = _led8n_format(line1, 8)
        t = _led8n_format(line2, 8) if line2 else "0" * 8
        return (p + t).encode("ascii")

    l1 = _pad(line1)

    if lines == 1:
        if protocol == "crlf":
            return (l1 + "\r\n").encode("ascii", errors="replace")
        if protocol == "logic_ctrl":
            return b"\x0C" + l1.encode("ascii", errors="replace") + b"\r"
        if protocol == "esc_pos":
            return (b"\x1B\x40" + b"\x1F\x11"
                    + l1.encode("ascii", errors="replace"))
        if protocol == "posiflex":
            return (b"\x0C" + b"\x1B\x51\x41"
                    + l1.encode("ascii", errors="replace"))
        if protocol == "ba63":
            return (b"\x02" + b"\x30"
                    + l1.encode("ascii", errors="replace"))
        return b"\x0C" + l1.encode("ascii", errors="replace")

    # Two-line text display
    l2 = _pad(line2)

    if protocol == "crlf":
        return (l1 + "\r\n" + l2 + "\r\n").encode("ascii", errors="replace")
    if protocol == "logic_ctrl":
        return (b"\x0C"
                + l1.encode("ascii", errors="replace") + b"\r"
                + l2.encode("ascii", errors="replace") + b"\r")
    if protocol == "esc_pos":
        return (b"\x1B\x40" + b"\x1F\x11"
                + l1.encode("ascii", errors="replace")
                + b"\x0A"
                + l2.encode("ascii", errors="replace"))
    if protocol == "posiflex":
        return (b"\x0C" + b"\x1B\x51\x41"
                + l1.encode("ascii", errors="replace")
                + b"\x1B\x51\x42"
                + l2.encode("ascii", errors="replace"))
    if protocol == "ba63":
        return (b"\x02" + b"\x30"
                + l1.encode("ascii", errors="replace")
                + b"\x02" + b"\x34"
                + l2.encode("ascii", errors="replace"))
    # simple
    return (b"\x0C"
            + l1.encode("ascii", errors="replace")
            + l2.encode("ascii", errors="replace"))


class PoleDisplay:
    """Lazy-open serial connection to a 2-line pole display."""

    def __init__(self):
        self._ser      = None
        self._open_port = None   # track which port is currently open

    def _open(self, cfg: dict) -> bool:
        port = cfg.get("port")
        if not port:
            return False
        # Reopen if port changed or connection dropped
        if self._ser and self._ser.is_open and self._open_port == port:
            return True
        # Close stale connection
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self._open_port = None
        try:
            import serial
            self._ser = serial.Serial(
                port,
                baudrate = cfg["baud"],
                bytesize = cfg["databits"],
                parity   = cfg["parity"],
                stopbits = cfg["stopbits"],
                timeout  = 1,
            )
            self._open_port = port
            log.info("Pole display opened: %s %s %s%s%s",
                     port, cfg["baud"], cfg["databits"], cfg["parity"], int(cfg["stopbits"]))
            return True
        except Exception as e:
            log.error("Pole display open failed (%s): %s", port, e)
            self._ser = None
            return False

    def _write(self, data: bytes):
        cfg = _get_port_settings()
        try:
            if self._open(cfg):
                self._ser.write(data)
        except Exception as e:
            log.error("Pole display write error: %s", e)
            self._ser = None

    def show(self, line1: str, line2: str):
        cfg = _get_port_settings()
        if not cfg.get("port"):
            return
        packet = _build_packet(line1, line2, cfg["protocol"], cfg["lines"])
        log.debug("Pole → port=%s proto=%s hex=%s",
                  cfg["port"], cfg["protocol"], packet.hex())
        try:
            if self._open(cfg):
                self._ser.write(packet)
        except Exception as e:
            log.error("Pole display show error: %s", e)
            self._ser = None

    def clear(self):
        self._write(b"\x0C" + b" " * 40)

    def welcome(self, shop_name: str = "Welcome!"):
        self.show(shop_name[:WIDTH], "")

    def close(self):
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        self._ser = None


# ── Module-level singleton ────────────────────────────────────────────────────
_display = PoleDisplay()


def pole_show(line1: str, line2: str):
    _display.show(line1, line2)


def pole_clear():
    _display.clear()


def pole_welcome(shop_name: str = "Welcome!"):
    _display.welcome(shop_name)


def pole_close():
    _display.close()
