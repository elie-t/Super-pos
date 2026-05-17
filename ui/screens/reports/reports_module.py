"""Reports module — tabbed container for all report/utility screens."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal

from ui.screens.reports.menu_qr_tab import MenuQRTab


class ReportsModule(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:#1a3a5c;")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 12, 0)
        bar_lay.setSpacing(12)

        back_btn = QPushButton("←  Back")
        back_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);color:#fff;border:1px solid rgba(255,255,255,0.3);"
            "border-radius:4px;padding:4px 12px;font-size:12px;}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}"
        )
        back_btn.setFixedHeight(28)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self.back.emit)
        bar_lay.addWidget(back_btn)

        title = QLabel("Reports & Tools")
        title.setStyleSheet("color:#fff; font-size:15px; font-weight:700; margin-left:8px;")
        bar_lay.addWidget(title)
        bar_lay.addStretch()
        root.addWidget(bar)

        # ── Tabs ──────────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane{border:none; background:#f4f6fa;}
            QTabBar::tab{
                background:#dde4ed; color:#1a3a5c; border:none;
                padding:8px 20px; font-size:12px; font-weight:600;
                border-top-left-radius:6px; border-top-right-radius:6px;
                margin-right:2px;
            }
            QTabBar::tab:selected{background:#1a3a5c; color:#fff;}
            QTabBar::tab:hover:!selected{background:#c5d0de;}
        """)

        tabs.addTab(MenuQRTab(), "📱  Menu QR Code")
        # Future tabs can be added here

        root.addWidget(tabs)
