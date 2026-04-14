"""
USB Pole Display (Customer Display) — 2-line VFD/LCD
Communicates via serial (USB-to-serial or native USB-CDC).
Most displays: 20 chars × 2 lines, 9600 baud.
"""
from __future__ import annotations

WIDTH = 20   # characters per line

# Common VFD control bytes
_CLEAR   = b"\x0C"          # form-feed = clear screen on most VFDs
_HOME    = b"\x0B"          # vertical-tab = cursor home on some displays
_CR      = b"\r"
_NL      = b"\n"


def _pad(text: str, width: int = WIDTH) -> str:
    """Truncate or space-pad to exactly `width` chars."""
    return f"{str(text)[:width]:<{width}}"


def _get_port_settings() -> tuple[str, int] | tuple[None, None]:
    """Read pole display port and baud from Settings table."""
    try:
        from database.engine import get_session, init_db
        from database.models.items import Setting
        init_db()
        session = get_session()
        try:
            def _g(key, default=""):
                s = session.get(Setting, key)
                return s.value if s else default
            port = _g("pole_port", "")
            baud = int(_g("pole_baud", "9600") or "9600")
            return (port or None), baud
        finally:
            session.close()
    except Exception:
        return None, None


class PoleDisplay:
    """Lazy-open serial connection to a 2-line pole display."""

    def __init__(self):
        self._ser = None

    def _open(self):
        if self._ser and self._ser.is_open:
            return True
        port, baud = _get_port_settings()
        if not port:
            return False
        try:
            import serial
            self._ser = serial.Serial(port, baudrate=baud, timeout=1)
            return True
        except Exception:
            self._ser = None
            return False

    def _write(self, data: bytes):
        try:
            if self._open():
                self._ser.write(data)
        except Exception:
            self._ser = None   # force reconnect next time

    def show(self, line1: str, line2: str):
        """Display two lines (each truncated/padded to 20 chars)."""
        l1 = _pad(line1)
        l2 = _pad(line2)
        self._write(_CLEAR + l1.encode("ascii", errors="replace")
                    + _CR + _NL
                    + l2.encode("ascii", errors="replace"))

    def clear(self):
        self._write(_CLEAR + b"                    \r\n                    ")

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
