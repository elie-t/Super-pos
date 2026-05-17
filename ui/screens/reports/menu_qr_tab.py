"""
Menu QR tab — generates an HTML menu, uploads to Supabase Storage,
and displays a scannable QR code pointing to the public URL.
"""
from __future__ import annotations
import os
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFrame, QScrollArea,
    QLineEdit, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QPixmap


# ── Worker signals ────────────────────────────────────────────────────────────

class _Sig(QObject):
    progress = Signal(str)
    done     = Signal(str, bytes, bytes)   # public_url, html_bytes, qr_png_bytes
    error    = Signal(str)


# ── Tab widget ────────────────────────────────────────────────────────────────

class MenuQRTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qr_png: bytes | None     = None
        self._html:   bytes | None     = None
        self._url:    str              = ""
        self._sig = _Sig()
        self._sig.progress.connect(self._on_progress)
        self._sig.done.connect(self._on_done)
        self._sig.error.connect(self._on_error)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # ── Title & description ───────────────────────────────────────────────
        title = QLabel("QR Code Menu Generator")
        title.setStyleSheet("font-size:16px; font-weight:800; color:#1a3a5c;")
        root.addWidget(title)

        desc = QLabel(
            "Generates a mobile-friendly menu from all active items, uploads it online, "
            "and creates a QR code your customers can scan to browse the catalog.\n"
            "Requires a public Supabase Storage bucket named  menu  (create once in your Supabase dashboard → Storage)."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:12px; color:#5a7090;")
        root.addWidget(desc)

        # ── Generate button + progress ────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("⚡  Generate & Upload Menu")
        self._gen_btn.setFixedHeight(40)
        self._gen_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;font-size:14px;font-weight:700;"
            "border:none;border-radius:6px;padding:0 20px;}"
            "QPushButton:hover{background:#1a6cb5;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._gen_btn.setCursor(Qt.PointingHandCursor)
        self._gen_btn.clicked.connect(self._start_generation)
        btn_row.addWidget(self._gen_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self._progress = QLabel("")
        self._progress.setStyleSheet("font-size:12px; color:#1a6cb5; font-weight:600;")
        root.addWidget(self._progress)

        # ── Divider ───────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#dde4ed;")
        root.addWidget(sep)

        # ── Result area (QR + URL + save buttons) ─────────────────────────────
        result = QHBoxLayout()
        result.setSpacing(24)

        # QR image
        self._qr_label = QLabel()
        self._qr_label.setFixedSize(220, 220)
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setStyleSheet(
            "border:2px dashed #c5d0de; border-radius:8px; color:#9aabbf; font-size:12px;"
        )
        self._qr_label.setText("QR code\nappears here")
        result.addWidget(self._qr_label)

        # URL + actions
        info = QVBoxLayout()
        info.setSpacing(10)
        info.setAlignment(Qt.AlignTop)

        url_lbl = QLabel("Menu URL:")
        url_lbl.setStyleSheet("font-size:11px; font-weight:700; color:#1a3a5c;")
        info.addWidget(url_lbl)

        url_row = QHBoxLayout()
        self._url_field = QLineEdit()
        self._url_field.setReadOnly(True)
        self._url_field.setPlaceholderText("URL will appear after generation…")
        self._url_field.setFixedHeight(30)
        self._url_field.setStyleSheet(
            "font-size:11px; background:#f4f6fa; border:1px solid #c5ccd6;"
            "border-radius:4px; padding:0 6px;"
        )
        url_row.addWidget(self._url_field)

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedSize(54, 30)
        copy_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:none;border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#1a3a5c;}"
        )
        copy_btn.clicked.connect(self._copy_url)
        url_row.addWidget(copy_btn)
        info.addLayout(url_row)

        save_qr_btn = QPushButton("💾  Save QR as Image")
        save_qr_btn.setFixedHeight(32)
        save_qr_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;border:none;border-radius:5px;"
            "font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        save_qr_btn.setEnabled(False)
        save_qr_btn.setCursor(Qt.PointingHandCursor)
        save_qr_btn.clicked.connect(self._save_qr)
        self._save_qr_btn = save_qr_btn
        info.addWidget(save_qr_btn)

        save_html_btn = QPushButton("🌐  Save Menu HTML")
        save_html_btn.setFixedHeight(32)
        save_html_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;border-radius:5px;"
            "font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#263238;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        save_html_btn.setEnabled(False)
        save_html_btn.setCursor(Qt.PointingHandCursor)
        save_html_btn.clicked.connect(self._save_html)
        self._save_html_btn = save_html_btn
        info.addWidget(save_html_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("font-size:11px; color:#5a7090;")
        info.addWidget(self._status_lbl)

        info.addStretch()
        result.addLayout(info)
        result.addStretch()

        root.addLayout(result)
        root.addStretch()

    # ── Generation logic ──────────────────────────────────────────────────────

    def _start_generation(self):
        self._gen_btn.setEnabled(False)
        self._save_qr_btn.setEnabled(False)
        self._save_html_btn.setEnabled(False)
        self._qr_label.setText("Generating…")
        self._qr_label.setPixmap(QPixmap())
        self._url_field.clear()
        self._status_lbl.clear()
        self._progress.setText("⏳  Building menu from database…")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            from utils.menu_generator import fetch_menu_data, build_menu_html, generate_qr_png, _get_shop_name
            from sync.service import upload_to_storage, is_configured

            self._sig.progress.emit("⏳  Loading items and categories…")
            categories = fetch_menu_data()
            total_items = sum(len(c["items"]) for c in categories)

            self._sig.progress.emit(f"⏳  Building HTML ({total_items} items, {len(categories)} categories)…")
            shop_name = _get_shop_name()
            html_str  = build_menu_html(categories, shop_name)
            html_bytes = html_str.encode("utf-8")

            public_url = ""

            # ── Try Supabase Storage upload ───────────────────────────────────
            if is_configured():
                self._sig.progress.emit("⏳  Uploading to Supabase Storage…")
                ok, result = upload_to_storage(
                    "menu", "menu.html", html_bytes, content_type="text/html; charset=utf-8"
                )
                if ok:
                    public_url = result
                else:
                    self._sig.progress.emit(f"⚠  Upload failed: {result[:80]}")

            # ── Auto-save to SNAPSHOT_SHARE_PATH if configured ────────────────
            self._try_save_to_share(html_bytes)

            # ── Generate QR ───────────────────────────────────────────────────
            self._sig.progress.emit("⏳  Generating QR code…")
            qr_url = public_url or f"Saved locally — {len(html_bytes):,} bytes"
            if public_url:
                qr_png = generate_qr_png(public_url)
            else:
                qr_png = generate_qr_png("https://tannourymarket.com")   # placeholder

            self._sig.done.emit(public_url, html_bytes, qr_png)

        except Exception as e:
            import traceback
            self._sig.error.emit(str(e) + "\n" + traceback.format_exc()[-400:])

    def _try_save_to_share(self, html_bytes: bytes):
        try:
            from config import SNAPSHOT_SHARE_PATH
            if not SNAPSHOT_SHARE_PATH:
                return
            path = os.path.expanduser(SNAPSHOT_SHARE_PATH)
            os.makedirs(path, exist_ok=True)
            dest = os.path.join(path, "menu.html")
            with open(dest, "wb") as f:
                f.write(html_bytes)
        except Exception:
            pass

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_progress(self, msg: str):
        self._progress.setText(msg)

    def _on_done(self, public_url: str, html_bytes: bytes, qr_png: bytes):
        self._gen_btn.setEnabled(True)
        self._qr_png  = qr_png
        self._html    = html_bytes
        self._url     = public_url

        # Show QR image
        pix = QPixmap()
        pix.loadFromData(qr_png)
        self._qr_label.setPixmap(pix.scaled(
            self._qr_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        ))

        self._url_field.setText(public_url or "Upload failed — HTML saved locally only")
        self._save_qr_btn.setEnabled(True)
        self._save_html_btn.setEnabled(True)

        if public_url:
            self._progress.setText("✅  Menu uploaded and QR ready!")
            self._status_lbl.setText(
                "Customers can scan this QR code to browse your menu on their phone. "
                "Re-generate any time to update prices."
            )
        else:
            self._progress.setText("✅  HTML generated (offline — not uploaded)")
            self._status_lbl.setText(
                "Supabase not configured or upload failed. Save the HTML manually and host it online to get a scannable QR."
            )

    def _on_error(self, msg: str):
        self._gen_btn.setEnabled(True)
        self._progress.setText("❌  Error during generation.")
        self._status_lbl.setText(msg[:300])

    # ── Save helpers ──────────────────────────────────────────────────────────

    def _copy_url(self):
        if self._url:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._url)
            self._status_lbl.setText("URL copied to clipboard.")

    def _save_qr(self):
        if not self._qr_png:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save QR Code", "menu_qr.png", "PNG Image (*.png)"
        )
        if path:
            with open(path, "wb") as f:
                f.write(self._qr_png)
            self._status_lbl.setText(f"QR saved: {path}")

    def _save_html(self):
        if not self._html:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Menu HTML", "menu.html", "HTML File (*.html)"
        )
        if path:
            with open(path, "wb") as f:
                f.write(self._html)
            self._status_lbl.setText(f"HTML saved: {path}")
