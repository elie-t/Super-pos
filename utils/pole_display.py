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
                "databits": int(_g("pole_databits", "8")     or "8"),
                "parity":   _g("pole_parity", "N"),
                "stopbits": float(_g("pole_stopbits", "1")   or "1"),
            }
        finally:
            session.close()
    except Exception:
        return {"port": None, "baud": 9600, "protocol": "simple",
                "databits": 8, "parity": "N", "stopbits": 1.0}


def _build_packet(line1: str, line2: str, protocol: str) -> bytes:
    """Return the byte sequence to display two lines on the pole."""
    l1 = _pad(line1)
    l2 = _pad(line2)

    if protocol == "crlf":
        # Plain CR/LF — cursor wraps automatically on many dumb terminals
        return (l1 + "\r\n" + l2 + "\r\n").encode("ascii", errors="replace")

    if protocol == "logic_ctrl":
        # Logic Controls LD9000 / CD5220 style
        # \x0C = clear;  write line1 then CR, write line2 then CR
        return (b"\x0C"
                + l1.encode("ascii", errors="replace") + b"\r"
                + l2.encode("ascii", errors="replace") + b"\r")

    if protocol == "esc_pos":
        # Epson DM-D110/210 / ESC-POS customer display
        # ESC @ = init;  \x1F\x11 = cursor home;  \x0A = LF moves to line 2
        return (b"\x1B\x40"                              # ESC @ init
                + b"\x1F\x11"                            # cursor home
                + l1.encode("ascii", errors="replace")
                + b"\x0A"                                # LF → line 2
                + l2.encode("ascii", errors="replace"))

    if protocol == "posiflex":
        # Posiflex / IEE style: ESC Q A = go to line 1, ESC Q B = line 2
        return (b"\x0C"
                + b"\x1B\x51\x41"                        # cursor to line 1
                + l1.encode("ascii", errors="replace")
                + b"\x1B\x51\x42"                        # cursor to line 2
                + l2.encode("ascii", errors="replace"))

    if protocol == "ba63":
        # BA63 / Bixolon BCD-1000 style — overwrite mode, 20-char fixed lines
        # No clear needed; two 20-char blocks written at address 0 and 20
        return (b"\x02"                                  # STX
                + b"\x30"                                # row 1 address
                + l1.encode("ascii", errors="replace")
                + b"\x02"
                + b"\x34"                                # row 2 address (0x34 = 52 = 32+20)
                + l2.encode("ascii", errors="replace"))

    # "simple" (default) — original behaviour: \x0C clear + 40-char block
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
        packet = _build_packet(line1, line2, cfg["protocol"])
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
