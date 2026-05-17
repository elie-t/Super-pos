"""
Menu QR tab:
  1. Generate an HTML menu file and save it to the OneDrive folder.
  2. User pastes their OneDrive share link → QR code is generated.
  3. Print / save the QR so customers can scan it to open the menu.
"""
from __future__ import annotations
import os
import threading

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QFrame,
    QGroupBox,
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QPixmap

from config import SNAPSHOT_SHARE_PATH


class _Sig(QObject):
    html_done  = Signal(str)   # saved path
    html_error = Signal(str)
    qr_ready   = Signal(bytes)


class MenuQRTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qr_png: bytes | None = None
        self._sig = _Sig()
        self._sig.html_done.connect(self._on_html_done)
        self._sig.html_error.connect(self._on_html_error)
        self._sig.qr_ready.connect(self._on_qr_ready)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel("QR Code Menu Generator")
        title.setStyleSheet("font-size:16px; font-weight:800; color:#1a3a5c;")
        root.addWidget(title)

        desc = QLabel(
            "Step 1: Generate the HTML menu and save it to your OneDrive folder.\n"
            "Step 2: Open OneDrive, share the file, copy the link, and paste it here.\n"
            "Step 3: Generate the QR — print it and display it in your shop."
        )
        desc.setStyleSheet("font-size:12px; color:#5a7090;")
        root.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#dde4ed;")
        root.addWidget(sep)

        # ── Step 1: Generate HTML ─────────────────────────────────────────────
        g1 = QGroupBox("Step 1 — Generate HTML Menu")
        g1.setStyleSheet(
            "QGroupBox{font-size:12px;font-weight:700;color:#1a3a5c;"
            "border:1px solid #c5ccd6;border-radius:6px;margin-top:6px;padding-top:10px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
        )
        g1_lay = QVBoxLayout(g1)
        g1_lay.setSpacing(8)

        path_row = QHBoxLayout()
        path_lbl = QLabel("Save to:")
        path_lbl.setFixedWidth(60)
        path_lbl.setStyleSheet("font-size:11px; font-weight:600;")
        path_row.addWidget(path_lbl)

        default_path = (os.path.expanduser(SNAPSHOT_SHARE_PATH)
                        if SNAPSHOT_SHARE_PATH else os.path.expanduser("~/OneDrive"))
        self._path_field = QLineEdit(default_path)
        self._path_field.setFixedHeight(28)
        self._path_field.setStyleSheet(
            "font-size:11px; border:1px solid #c5ccd6; border-radius:4px; padding:0 6px;"
        )
        path_row.addWidget(self._path_field)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedSize(70, 28)
        browse_btn.setStyleSheet(
            "QPushButton{background:#455a64;color:#fff;border:none;border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#263238;}"
        )
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(browse_btn)
        g1_lay.addLayout(path_row)

        gen_row = QHBoxLayout()
        self._gen_btn = QPushButton("🌐  Generate HTML Menu")
        self._gen_btn.setFixedHeight(38)
        self._gen_btn.setStyleSheet(
            "QPushButton{background:#1a3a5c;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:6px;padding:0 20px;}"
            "QPushButton:hover{background:#1a6cb5;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._gen_btn.setCursor(Qt.PointingHandCursor)
        self._gen_btn.clicked.connect(self._generate_html)
        gen_row.addWidget(self._gen_btn)

        self._html_status = QLabel("")
        self._html_status.setStyleSheet("font-size:11px; color:#2e7d32; font-weight:600;")
        gen_row.addWidget(self._html_status)
        gen_row.addStretch()
        g1_lay.addLayout(gen_row)
        root.addWidget(g1)

        # ── Step 2: QR from share link ────────────────────────────────────────
        g2 = QGroupBox("Step 2 — Generate QR from Share Link")
        g2.setStyleSheet(
            "QGroupBox{font-size:12px;font-weight:700;color:#1a3a5c;"
            "border:1px solid #c5ccd6;border-radius:6px;margin-top:6px;padding-top:10px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
        )
        g2_lay = QVBoxLayout(g2)
        g2_lay.setSpacing(10)

        hint = QLabel(
            "Open OneDrive → right-click menu.html → Share → Anyone with the link → Copy link"
        )
        hint.setStyleSheet("font-size:11px; color:#5a7090; font-style:italic;")
        g2_lay.addWidget(hint)

        url_row = QHBoxLayout()
        url_lbl = QLabel("Link:")
        url_lbl.setFixedWidth(40)
        url_lbl.setStyleSheet("font-size:11px; font-weight:600;")
        url_row.addWidget(url_lbl)

        self._url_field = QLineEdit()
        self._url_field.setPlaceholderText("https://onedrive.live.com/…  or any public URL")
        self._url_field.setFixedHeight(28)
        self._url_field.setStyleSheet(
            "font-size:11px; border:1px solid #c5ccd6; border-radius:4px; padding:0 6px;"
        )
        self._url_field.textChanged.connect(lambda t: self._qr_btn.setEnabled(bool(t.strip())))
        url_row.addWidget(self._url_field)
        g2_lay.addLayout(url_row)

        self._qr_btn = QPushButton("🔲  Generate QR Code")
        self._qr_btn.setFixedHeight(38)
        self._qr_btn.setEnabled(False)
        self._qr_btn.setStyleSheet(
            "QPushButton{background:#2e7d32;color:#fff;font-size:13px;font-weight:700;"
            "border:none;border-radius:6px;padding:0 20px;}"
            "QPushButton:hover{background:#1b5e20;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._qr_btn.setCursor(Qt.PointingHandCursor)
        self._qr_btn.clicked.connect(self._make_qr)
        g2_lay.addWidget(self._qr_btn)
        root.addWidget(g2)

        # ── QR result ─────────────────────────────────────────────────────────
        qr_area = QHBoxLayout()
        qr_area.setSpacing(20)

        self._qr_label = QLabel("QR code\nappears here")
        self._qr_label.setFixedSize(200, 200)
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setStyleSheet(
            "border:2px dashed #c5d0de; border-radius:8px; color:#9aabbf; font-size:11px;"
        )
        qr_area.addWidget(self._qr_label)

        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignTop)
        btn_col.setSpacing(8)

        self._save_qr_btn = QPushButton("💾  Save QR as PNG")
        self._save_qr_btn.setFixedHeight(34)
        self._save_qr_btn.setEnabled(False)
        self._save_qr_btn.setStyleSheet(
            "QPushButton{background:#1a6cb5;color:#fff;border:none;border-radius:5px;"
            "font-size:12px;font-weight:600;padding:0 14px;}"
            "QPushButton:hover{background:#1a3a5c;}"
            "QPushButton:disabled{background:#aaa;}"
        )
        self._save_qr_btn.clicked.connect(self._save_qr)
        btn_col.addWidget(self._save_qr_btn)

        self._qr_info = QLabel("")
        self._qr_info.setWordWrap(True)
        self._qr_info.setStyleSheet("font-size:11px; color:#5a7090;")
        btn_col.addWidget(self._qr_info)
        btn_col.addStretch()

        qr_area.addLayout(btn_col)
        qr_area.addStretch()
        root.addLayout(qr_area)
        root.addStretch()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select OneDrive Folder",
                                                   self._path_field.text())
        if folder:
            self._path_field.setText(folder)

    # ── HTML generation (background thread) ───────────────────────────────────

    def _generate_html(self):
        self._gen_btn.setEnabled(False)
        self._html_status.setText("⏳  Generating…")
        self._html_status.setStyleSheet("font-size:11px; color:#1a6cb5; font-weight:600;")
        folder = self._path_field.text().strip()
        threading.Thread(target=self._html_worker, args=(folder,), daemon=True).start()

    def _html_worker(self, folder: str):
        try:
            from utils.menu_generator import fetch_menu_data, get_shop_name, build_menu_html
            categories = fetch_menu_data()
            shop_name  = get_shop_name()
            html_bytes = build_menu_html(categories, shop_name).encode("utf-8")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "menu.html")
            with open(path, "wb") as f:
                f.write(html_bytes)
            self._sig.html_done.emit(path)
        except Exception as e:
            self._sig.html_error.emit(str(e))

    def _on_html_done(self, path: str):
        self._gen_btn.setEnabled(True)
        self._html_status.setText(f"✅  Saved: {os.path.basename(path)}")
        self._html_status.setStyleSheet("font-size:11px; color:#2e7d32; font-weight:600;")

    def _on_html_error(self, msg: str):
        self._gen_btn.setEnabled(True)
        self._html_status.setText(f"❌  {msg[:120]}")
        self._html_status.setStyleSheet("font-size:11px; color:#c62828; font-weight:600;")

    # ── QR generation ────────────────────────────────────────────────────────

    def _make_qr(self):
        url = self._url_field.text().strip()
        if not url:
            return
        try:
            from utils.menu_generator import generate_qr_png
            self._sig.qr_ready.emit(generate_qr_png(url))
        except Exception as e:
            self._qr_info.setText(f"QR error: {e}")

    def _on_qr_ready(self, png: bytes):
        self._qr_png = png
        pix = QPixmap()
        pix.loadFromData(png)
        self._qr_label.setPixmap(
            pix.scaled(self._qr_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self._save_qr_btn.setEnabled(True)
        self._qr_info.setText("Customers scan this QR to open the menu on their phone.")

    def _save_qr(self):
        if not self._qr_png:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save QR Code", "menu_qr.png",
                                               "PNG Image (*.png)")
        if path:
            with open(path, "wb") as f:
                f.write(self._qr_png)
            self._qr_info.setText(f"Saved: {path}")
