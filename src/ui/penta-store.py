#!/usr/bin/env python3
"""
Penta Store - Graphical Application Manager
============================================
Qt6/PySide6-based GUI for browsing, searching, and installing
software from all connected Penta OS sources.

Features:
  - Search bar with live results from Penta Hub.
  - Package details (version, source, description).
  - One‑click Install with progress log.
  - Installed applications list.
  - Mode Switcher panel (stub).

Usage:
    python3 src/ui/penta-store.py
"""

import sys
import requests
import threading
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QTextEdit, QSplitter, QTabWidget, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject

# ---------- Configuration ----------
HUB_URL = "http://localhost:8400"
RESOLVER_URL = "http://localhost:8500"

# ---------- Worker Signals ----------
class WorkerSignals(QObject):
    """Defines signals for background tasks."""
    search_done = Signal(list)            # results list
    install_log = Signal(str)            # log line
    install_progress = Signal(int)       # 0-100
    install_done = Signal(bool, str)     # success, message

# ---------- Main Window ----------
class PentaStoreWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Penta Store")
        self.resize(900, 600)

        # Central widget with tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ---- Store Tab ----
        self.store_tab = QWidget()
        self.tabs.addTab(self.store_tab, "Store")

        store_layout = QVBoxLayout(self.store_tab)

        # Search bar and install button
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search software (e.g., firefox, metasploit)...")
        self.search_input.returnPressed.connect(self.perform_search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.perform_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_button)
        store_layout.addLayout(search_layout)

        # Splitter for results and details
        splitter = QSplitter(Qt.Horizontal)

        # Results list
        self.results_list = QListWidget()
        self.results_list.itemClicked.connect(self.show_package_details)
        splitter.addWidget(self.results_list)

        # Details panel
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        self.details_label = QLabel("Select a package to see details.")
        self.details_label.setWordWrap(True)
        self.install_button = QPushButton("Install")
        self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.start_install)
        details_layout.addWidget(self.details_label)
        details_layout.addWidget(self.install_button)
        details_layout.addStretch()
        splitter.addWidget(details_widget)

        store_layout.addWidget(splitter, 1)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        store_layout.addWidget(QLabel("Installation Log:"))
        store_layout.addWidget(self.log_output)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        store_layout.addWidget(self.progress_bar)

        # ---- Installed Tab ----
        self.installed_tab = QWidget()
        self.tabs.addTab(self.installed_tab, "Installed")
        installed_layout = QVBoxLayout(self.installed_tab)
        self.installed_list = QListWidget()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_installed)
        installed_layout.addWidget(QLabel("Installed Applications:"))
        installed_layout.addWidget(self.installed_list)
        installed_layout.addWidget(refresh_btn)

        # ---- Mode Switcher Tab ----
        self.mode_tab = QWidget()
        self.tabs.addTab(self.mode_tab, "Modes")
        mode_layout = QVBoxLayout(self.mode_tab)
        mode_layout.addWidget(QLabel("Select Mode:"))
        modes = ["desktop", "phone", "pentest", "server", "router", "smarthome", "ai"]
        for mode in modes:
            btn = QPushButton(mode.capitalize())
            btn.clicked.connect(lambda checked, m=mode: self.switch_mode(m))
            mode_layout.addWidget(btn)
        mode_layout.addStretch()

        # Worker signals
        self.signals = WorkerSignals()
        self.signals.search_done.connect(self.on_search_done)
        self.signals.install_log.connect(self.on_install_log)
        self.signals.install_progress.connect(self.on_install_progress)
        self.signals.install_done.connect(self.on_install_done)

        # Store currently selected package info
        self.current_package = None

        # Load installed list on startup
        self.load_installed()

    # ---------- Search ----------
    def perform_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        # Run search in background thread
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            r = requests.get(f"{HUB_URL}/api/v1/search", params={"q": query, "limit": 20})
            r.raise_for_status()
            results = r.json().get("results", [])
            self.signals.search_done.emit(results)
        except Exception as e:
            self.signals.search_done.emit([])
            self.signals.install_log.emit(f"Search error: {e}")

    def on_search_done(self, results):
        self.results_list.clear()
        if not results:
            self.results_list.addItem("No results found.")
            return
        for pkg in results:
            item_text = f"{pkg['name']} ({pkg['source']}) - {pkg.get('version','?')}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, pkg)
            self.results_list.addItem(item)

    # ---------- Package Details ----------
    def show_package_details(self, item):
        pkg = item.data(Qt.UserRole)
        if not pkg:
            return
        self.current_package = pkg
        details = (
            f"Name: {pkg['name']}\n"
            f"Source: {pkg['source']}\n"
            f"Version: {pkg.get('version', 'unknown')}\n"
            f"Description: {pkg.get('description', 'N/A')}\n"
            f"Container: {pkg.get('container', 'N/A')}"
        )
        self.details_label.setText(details)
        self.install_button.setEnabled(True)

    # ---------- Install ----------
    def start_install(self):
        if not self.current_package:
            return
        pkg = self.current_package
        self.install_button.setEnabled(False)
        self.log_output.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        threading.Thread(target=self._install_thread, args=(pkg,), daemon=True).start()

    def _install_thread(self, pkg):
        try:
            payload = {"package": pkg["name"], "source": pkg["source"]}
            r = requests.post(f"{RESOLVER_URL}/api/v1/install", json=payload)
            r.raise_for_status()
            task_id = r.json()["task_id"]
            # Poll for updates
            last_progress = 0
            while True:
                time.sleep(0.5)
                tr = requests.get(f"{RESOLVER_URL}/api/v1/task/{task_id}")
                task = tr.json()
                new_progress = task.get("progress", 0)
                if new_progress != last_progress:
                    self.signals.install_progress.emit(new_progress)
                    last_progress = new_progress
                # Emit new log lines
                logs = task.get("log", [])
                if logs:
                    self.signals.install_log.emit(logs[-1])  # latest line
                if task["status"] in ("completed", "failed"):
                    self.signals.install_progress.emit(100 if task["status"] == "completed" else 0)
                    self.signals.install_done.emit(
                        task["status"] == "completed",
                        task.get("result", "")
                    )
                    break
        except Exception as e:
            self.signals.install_done.emit(False, str(e))

    def on_install_log(self, text):
        self.log_output.append(text)

    def on_install_progress(self, value):
        self.progress_bar.setValue(value)

    def on_install_done(self, success, message):
        self.progress_bar.setVisible(False)
        self.install_button.setEnabled(True)
        if success:
            QMessageBox.information(self, "Installation Complete", f"Installed successfully.\n{message}")
            self.load_installed()
        else:
            QMessageBox.critical(self, "Installation Failed", f"Error: {message}")

    # ---------- Installed List ----------
    def load_installed(self):
        try:
            r = requests.get(f"{RESOLVER_URL}/api/v1/installed")
            r.raise_for_status()
            apps = r.json().get("installed", [])
            self.installed_list.clear()
            if not apps:
                self.installed_list.addItem("No applications installed.")
                return
            for app in apps:
                self.installed_list.addItem(app["name"])
        except Exception as e:
            self.installed_list.clear()
            self.installed_list.addItem(f"Could not load: {e}")

    # ---------- Mode Switch ----------
    def switch_mode(self, mode):
        try:
            r = requests.post(f"{RESOLVER_URL}/api/v1/mode/switch", params={"mode": mode})
            r.raise_for_status()
            QMessageBox.information(self, "Mode Switch", f"Mode switched to '{mode}'.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not switch mode: {e}")

# ---------- Entry Point ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PentaStoreWindow()
    window.show()
    sys.exit(app.exec())
