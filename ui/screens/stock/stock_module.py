"""
Stock module container — manages navigation between all stock sub-screens.
Each sub-screen is its own file; this file only handles routing.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Signal

from ui.screens.stock.stock_hub        import StockHub
from ui.screens.stock.items_list       import ItemsListScreen
from ui.screens.stock.item_maintenance import ItemMaintenanceScreen
from ui.screens.stock.categories       import CategoriesScreen
from ui.screens.stock.brands           import BrandsScreen
from ui.screens.stock.warehouse_table  import WarehouseTableScreen
from ui.screens.stock.stock_card       import StockCardScreen
from ui.screens.stock.warehouse_transfer_screen import WarehouseTransferScreen


class StockModule(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        # Hub is always index 0
        self._hub = StockHub()
        self._hub.tool_requested.connect(self._open_tool)
        self._stack.addWidget(self._hub)

        # Cached sub-screens (created on first use)
        self._screens: dict[str, QWidget] = {}

    # ── Navigation ────────────────────────────────────────────────────────────

    def _open_tool(self, key: str):
        if key == "items_list":
            self._show("items_list", self._make_items_list)
        elif key == "item_maintenance":
            self._show_item_maintenance("")
        elif key == "categories":
            self._show("categories", lambda: self._make_categories(False))
        elif key == "subcategories":
            self._show("subcategories", lambda: self._make_categories(True))
        elif key == "brands":
            self._show("brands", lambda: BrandsScreen())
        elif key == "warehouse_table":
            self._show("warehouse_table", lambda: WarehouseTableScreen())
        elif key == "stock_card":
            self._show("stock_card", lambda: StockCardScreen())
        elif key == "warehouse_transfer":
            self._show("warehouse_transfer", lambda: WarehouseTransferScreen())
        elif key == "inventory_invoice":
            self._show("inventory_invoice", lambda: self._make_inventory_session())
        elif key == "old_inventory":
            self._show("old_inventory", lambda: self._make_inventory())
        elif key == "import_items":
            self._run_import()
        else:
            # Placeholder for upcoming screens
            from PySide6.QtWidgets import QLabel
            placeholder = QWidget()
            from PySide6.QtWidgets import QVBoxLayout
            pl = QVBoxLayout(placeholder)
            lbl = QLabel(f"'{key}' — coming soon")
            lbl.setStyleSheet("font-size:18px; color:#888; margin:40px;")
            back_btn = __import__('PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton("← Back")
            back_btn.setObjectName("secondaryBtn")
            back_btn.setFixedWidth(100)
            back_btn.clicked.connect(self._go_hub)
            pl.addWidget(back_btn)
            pl.addWidget(lbl)
            self._stack.addWidget(placeholder)
            self._stack.setCurrentWidget(placeholder)

    def _show(self, key: str, factory):
        if key not in self._screens:
            screen = factory()
            self._wire_back(screen)
            self._screens[key] = screen
            self._stack.addWidget(screen)
        else:
            # Refresh data on re-open
            if hasattr(self._screens[key], "refresh"):
                self._screens[key].refresh()
        self._stack.setCurrentWidget(self._screens[key])

    def _show_item_maintenance(self, item_id: str):
        """Always create a fresh maintenance screen (new or existing item)."""
        screen = ItemMaintenanceScreen(item_id=item_id)
        screen.back.connect(self._go_hub)
        screen.saved.connect(lambda iid: self._after_item_save(iid))
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)

    def _after_item_save(self, item_id: str):
        # Refresh items list if open
        if "items_list" in self._screens:
            self._screens["items_list"].refresh()

    def _wire_back(self, screen: QWidget):
        """Connect back signal if the screen has one."""
        if hasattr(screen, "back"):
            screen.back.connect(self._go_hub)
        if hasattr(screen, "open_item_requested"):
            screen.open_item_requested.connect(self._show_item_maintenance)
        if hasattr(screen, "add_item_requested"):
            screen.add_item_requested.connect(lambda: self._show_item_maintenance(""))
        if hasattr(screen, "edit_item_requested"):
            screen.edit_item_requested.connect(
                lambda iid, s=screen: self._open_item_maintenance_from(iid, s)
            )

    def _open_item_maintenance_from(self, item_id: str, return_to: QWidget):
        """Open item maintenance; pressing Back returns to return_to screen."""
        screen = ItemMaintenanceScreen(item_id=item_id)
        screen.back.connect(lambda: self._close_item_maintenance_to(screen, return_to))
        screen.saved.connect(lambda _: self._close_item_maintenance_to(screen, return_to))
        self._stack.addWidget(screen)
        self._stack.setCurrentWidget(screen)

    def _close_item_maintenance_to(self, maint_screen: QWidget, return_to: QWidget):
        self._stack.setCurrentWidget(return_to)
        self._stack.removeWidget(maint_screen)
        maint_screen.deleteLater()

    def _go_hub(self):
        self._stack.setCurrentWidget(self._hub)

    def _make_items_list(self):
        return ItemsListScreen()

    def _make_inventory(self):
        from ui.screens.stock.inventory_screen import InventoryScreen
        return InventoryScreen()

    def _make_inventory_session(self):
        from ui.screens.stock.inventory_session_screen import InventorySessionScreen
        return InventorySessionScreen()

    def _make_categories(self, sub: bool):
        return CategoriesScreen(subcategories_mode=sub)

    def go_hub(self):
        self._go_hub()

    # ── Import from Excel ──────────────────────────────────────────────────────

    def _run_import(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
        from PySide6.QtCore import Qt, QThread, QObject, Signal as Sig

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel file", "", "Excel files (*.xlsx *.xls)"
        )
        if not path:
            return

        reply = QMessageBox.question(
            self, "Clear existing items?",
            "Do you want to DELETE all existing items and reimport from scratch?\n\n"
            "Choose No to only add new items (skip duplicates by title).",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Cancel:
            return
        do_clear = (reply == QMessageBox.Yes)

        # Run in a background thread so the UI stays responsive
        class Worker(QObject):
            finished = Sig(str)   # summary text
            error    = Sig(str)

            def __init__(self, p, c):
                super().__init__()
                self._path = p
                self._clear = c

            def run(self):
                try:
                    import sys, pathlib
                    sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
                    from seed.import_items import import_items as do_import
                    import io, contextlib
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        do_import(self._path, batch_size=500, do_clear=self._clear)
                    self.finished.emit(buf.getvalue())
                except Exception as exc:
                    self.error.emit(str(exc))

        progress = QProgressDialog("Importing items…", None, 0, 0, self)
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        thread = QThread(self)
        worker = Worker(path, do_clear)
        worker.moveToThread(thread)

        def on_done(msg):
            thread.quit()
            progress.close()
            # Refresh items list if open
            if "items_list" in self._screens:
                self._screens["items_list"].refresh()
            # Show last few lines of output
            lines = [l for l in msg.strip().splitlines() if l.strip()]
            summary = "\n".join(lines[-8:])
            QMessageBox.information(self, "Import complete", summary)

        def on_error(msg):
            thread.quit()
            progress.close()
            QMessageBox.critical(self, "Import failed", msg)

        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        thread.started.connect(worker.run)
        thread.start()
        self._import_thread = thread   # keep alive
