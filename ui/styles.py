"""
Global stylesheet — light professional theme, classic retail/POS style.
"""

APP_STYLE = """
/* ── Base ── */
QWidget {
    background-color: #f0f2f5;
    color: #1a1a2e;
    font-family: "Segoe UI", "SF Pro Text", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog {
    background-color: #f0f2f5;
}

/* ── Header bar ── */
#headerBar {
    background-color: #1a3a5c;
    border-bottom: 2px solid #0f2540;
    min-height: 48px;
    max-height: 48px;
}

#headerTitle {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 1px;
}

#headerUser {
    font-size: 12px;
    color: #a8c8e8;
}

#headerRole {
    font-size: 11px;
    font-weight: 700;
    color: #ffffff;
    background-color: #1565c0;
    border-radius: 4px;
    padding: 2px 10px;
}

/* ── Module tab bar ── */
#tabBar {
    background-color: #e8ecf0;
    border-bottom: 2px solid #c0c8d4;
    min-height: 36px;
    max-height: 36px;
}

QPushButton#tabBtn {
    background-color: transparent;
    color: #445566;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 6px 18px;
    font-size: 13px;
    font-weight: 500;
    border-radius: 0px;
}

QPushButton#tabBtn:hover {
    background-color: #d8e4f0;
    color: #1a3a5c;
}

QPushButton#tabBtn[active="true"] {
    color: #1a3a5c;
    font-weight: 700;
    border-bottom: 3px solid #1a6cb5;
    background-color: #ffffff;
}

/* ── Login card ── */
#loginCard {
    background-color: #ffffff;
    border: 1px solid #c8d4e0;
    border-radius: 10px;
}

#appTitle {
    font-size: 30px;
    font-weight: 700;
    color: #1a3a5c;
    letter-spacing: 2px;
}

#appSubtitle {
    font-size: 13px;
    color: #6680a0;
}

#loginLabel {
    font-size: 11px;
    color: #6680a0;
    font-weight: 600;
    letter-spacing: 0.5px;
}

/* ── Inputs ── */
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #c0ccd8;
    border-radius: 5px;
    padding: 8px 12px;
    font-size: 13px;
    color: #1a1a2e;
    selection-background-color: #1a6cb5;
    selection-color: #ffffff;
}

QLineEdit:focus {
    border: 1px solid #1a6cb5;
    background-color: #f4f8ff;
}

QLineEdit:read-only {
    background-color: #f0f2f5;
    color: #6680a0;
}

/* ── Primary button ── */
QPushButton#primaryBtn {
    background-color: #1a6cb5;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    padding: 10px 0px;
    font-size: 14px;
    font-weight: 600;
}

QPushButton#primaryBtn:hover   { background-color: #1a80d4; }
QPushButton#primaryBtn:pressed { background-color: #0f5090; }
QPushButton#primaryBtn:disabled {
    background-color: #c0ccd8;
    color: #ffffff;
}

/* ── Secondary button ── */
QPushButton#secondaryBtn {
    background-color: #ffffff;
    color: #445566;
    border: 1px solid #c0ccd8;
    border-radius: 5px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton#secondaryBtn:hover {
    border-color: #1a6cb5;
    color: #1a6cb5;
    background-color: #f0f6ff;
}

/* ── Success button ── */
QPushButton#successBtn {
    background-color: #2e7d32;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton#successBtn:hover   { background-color: #388e3c; }
QPushButton#successBtn:pressed { background-color: #1b5e20; }

/* ── Danger button ── */
QPushButton#dangerBtn {
    background-color: #c62828;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton#dangerBtn:hover   { background-color: #e53935; }
QPushButton#dangerBtn:pressed { background-color: #a01010; }

/* ── Warning button ── */
QPushButton#warningBtn {
    background-color: #e65100;
    color: #ffffff;
    border: none;
    border-radius: 5px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton#warningBtn:hover { background-color: #bf360c; }

/* ── Hub tiles (module/sub-module grid buttons) ── */
QPushButton#hubTile {
    background-color: #ffffff;
    color: #1a1a2e;
    border: 1px solid #c8d4e0;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    padding: 10px;
}

QPushButton#hubTile:hover {
    background-color: #e8f0fa;
    border-color: #1a6cb5;
    color: #1a3a5c;
}

QPushButton#hubTile:pressed {
    background-color: #d0e4f8;
    border-color: #0f5090;
}

/* ── Panel / card containers ── */
#panel {
    background-color: #ffffff;
    border: 1px solid #d0d8e4;
    border-radius: 6px;
}

#sectionTitle {
    font-size: 14px;
    font-weight: 700;
    color: #1a3a5c;
    padding: 4px 0px;
}

#sectionLabel {
    font-size: 10px;
    font-weight: 700;
    color: #8899aa;
    letter-spacing: 1px;
    text-transform: uppercase;
}

/* ── Tables ── */
QTableWidget, QTableView {
    background-color: #ffffff;
    alternate-background-color: #f5f8fc;
    border: 1px solid #d0d8e4;
    border-radius: 4px;
    gridline-color: #e4eaf0;
    selection-background-color: #1a6cb5;
    selection-color: #ffffff;
    outline: none;
}

QHeaderView::section {
    background-color: #e8ecf2;
    color: #445566;
    border: none;
    border-right: 1px solid #d0d8e4;
    border-bottom: 2px solid #c0ccd8;
    padding: 7px 10px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}

QTableWidget::item, QTableView::item {
    padding: 5px 10px;
    border: none;
    color: #1a1a2e;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #1a6cb5;
    color: #ffffff;
}

/* ── Scroll bars ── */
QScrollBar:vertical {
    background: #f0f2f5;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #b0bcc8;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #1a6cb5; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    background: #f0f2f5;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #b0bcc8;
    border-radius: 5px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── ComboBox ── */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #c0ccd8;
    border-radius: 5px;
    padding: 7px 12px;
    color: #1a1a2e;
    min-height: 20px;
}
QComboBox:focus { border-color: #1a6cb5; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #1a6cb5;
    selection-background-color: #e8f0fa;
    selection-color: #1a3a5c;
    outline: none;
}

/* ── CheckBox ── */
QCheckBox {
    spacing: 8px;
    color: #1a1a2e;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c0ccd8;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background-color: #1a6cb5;
    border-color: #1a6cb5;
}

/* ── Status bar ── */
QStatusBar {
    background-color: #1a3a5c;
    color: #a8c8e8;
    font-size: 11px;
    border-top: 1px solid #0f2540;
}

/* ── Error / info labels ── */
#errorLabel  { color: #c62828; font-size: 12px; }
#successLabel { color: #2e7d32; font-size: 12px; }
#infoLabel   { color: #1a6cb5; font-size: 12px; }

/* ── Search box ── */
#searchBox {
    background-color: #ffffff;
    border: 1px solid #c0ccd8;
    border-radius: 20px;
    padding: 7px 16px;
    font-size: 13px;
}
#searchBox:focus {
    border-color: #1a6cb5;
}

/* ── Dashboard tiles ── */
QPushButton#dashTile {
    background-color: #ffffff;
    border: 1px solid #c8d4e0;
    border-radius: 10px;
    text-align: center;
    color: #1a1a2e;
}
QPushButton#dashTile:hover {
    background-color: #e8f0fa;
    border-color: #1a6cb5;
}
QPushButton#dashTile:pressed {
    background-color: #d0e4f8;
}

#tileIcon  { font-size: 30px; background: transparent; border: none; }
#tileTitle { font-size: 14px; font-weight: 600; color: #1a1a2e; background: transparent; border: none; }
#tileLabel { font-size: 11px; color: #6680a0; background: transparent; border: none; }

/* ── Spinbox ── */
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    border: 1px solid #c0ccd8;
    border-radius: 5px;
    padding: 7px 8px;
    color: #1a1a2e;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #1a6cb5; }

/* ── GroupBox ── */
QGroupBox {
    border: 1px solid #d0d8e4;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: 600;
    color: #1a3a5c;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    background-color: #f0f2f5;
    color: #1a3a5c;
}

/* ── Tab widget ── */
QTabWidget::pane {
    border: 1px solid #d0d8e4;
    background: #ffffff;
    border-radius: 0 4px 4px 4px;
}
QTabBar::tab {
    background: #e8ecf2;
    border: 1px solid #d0d8e4;
    border-bottom: none;
    padding: 7px 18px;
    color: #445566;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #1a3a5c;
    font-weight: 700;
    border-top: 2px solid #1a6cb5;
}
QTabBar::tab:hover:!selected {
    background: #d8e8f8;
}

/* ── Splitter ── */
QSplitter::handle {
    background-color: #d0d8e4;
}
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical   { height: 2px; }

/* ── Toolbar-style action row ── */
#actionBar {
    background-color: #e8ecf2;
    border-bottom: 1px solid #d0d8e4;
    min-height: 40px;
    max-height: 40px;
}

QPushButton#actionBtn {
    background-color: transparent;
    color: #1a3a5c;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton#actionBtn:hover {
    background-color: #d0e0f0;
    border-color: #a0b8d0;
}
QPushButton#actionBtn:pressed {
    background-color: #b8d0e8;
}

/* ── Badge / count label ── */
#badge {
    background-color: #1a6cb5;
    color: #ffffff;
    border-radius: 10px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 700;
}
"""
