"""
USB/Serial Pole Display (Customer Display) — 2-line VFD/LCD
Supports the most common protocols used by built-in POS poles.
"""
from __future__ import annotations

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


def _build_packet(line1: str, line2: str, protocol: str, lines: int = 1) -> bytes:
    """Return the byte sequence to display on the pole.
    If lines==1, line2 is ignored and only line1 is sent."""
    l1 = _pad(line1)

    if lines == 1:
        # Single-line display: just send the first line
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
        # simple
        return b"\x0C" + l1.encode("ascii", errors="replace")

    # Two-line display
    l2 = _pad(line2)

    if protocol == "crlf":
        return (l1 + "\r\n" + l2 + "\r\n").encode("ascii", errors="replace")

    if protocol == "logic_ctrl":
        return (b"\x0C"
                + l1.encode("ascii", errors="replace") + b"\r"
                + l2.encode("ascii", errors="replace") + b"\r")

    if protocol == "esc_pos":
        return (b"\x1B\x40"
                + b"\x1F\x11"
                + l1.encode("ascii", errors="replace")
                + b"\x0A"
                + l2.encode("ascii", errors="replace"))

    if protocol == "posiflex":
        return (b"\x0C"
                + b"\x1B\x51\x41"
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
        self._ser = None

    def _open(self, cfg: dict) -> bool:
        if self._ser and self._ser.is_open:
            return True
        if not cfg.get("port"):
            return False
        try:
            import serial
            self._ser = serial.Serial(
                cfg["port"],
                baudrate = cfg["baud"],
                bytesize = cfg["databits"],
                parity   = cfg["parity"],
                stopbits = cfg["stopbits"],
                timeout  = 1,
            )
            return True
        except Exception:
            self._ser = None
            return False

    def _write(self, data: bytes):
        cfg = _get_port_settings()
        try:
            if self._open(cfg):
                self._ser.write(data)
        except Exception:
            self._ser = None

    def show(self, line1: str, line2: str):
        cfg = _get_port_settings()
        if not cfg.get("port"):
            return
        packet = _build_packet(line1, line2, cfg["protocol"], cfg["lines"])
        try:
            if self._open(cfg):
                self._ser.write(packet)
        except Exception:
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
