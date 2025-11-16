# -*- coding: utf-8 -*-
"""
History Panel Widget
"""

import os
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon, get_pixmap
from src.preview_cache import get_preview_cache


class HistoryPanel(QtWidgets.QWidget):
    """Panel for displaying ingestion history."""
    
    def __init__(self, db_manager, parent=None):
        super(HistoryPanel, self).__init__(parent)
        self.db = db_manager
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Ingestion History")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        title_layout.addWidget(title)
        
        # Export button
        export_btn = QtWidgets.QPushButton("Export CSV")
        export_btn.setObjectName('small')
        export_btn.setProperty('class', 'small')
        export_btn.clicked.connect(self.export_csv)
        title_layout.addWidget(export_btn)
        title_layout.addStretch()
        
        layout.addLayout(title_layout)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Date/Time', 'Action', 'Source', 'Target', 'Status'])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        # Refresh button
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.setIcon(get_icon('refresh', size=20))
        refresh_btn.setObjectName('primary')
        refresh_btn.setProperty('class', 'primary')
        refresh_btn.clicked.connect(self.load_history)
        layout.addWidget(refresh_btn)
    
    def load_history(self, limit=100):
        """Load history from database."""
        history = self.db.get_ingestion_history(limit)
        
        self.table.setRowCount(len(history))
        for row, entry in enumerate(history):
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(entry['ingested_at']))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(entry['action']))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(entry['source_path'] or ''))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(entry['target_list'] or ''))
            
            status_item = QtWidgets.QTableWidgetItem(entry['status'])
            if entry['status'] == 'error':
                status_item.setForeground(QtGui.QColor('red'))
            else:
                status_item.setForeground(QtGui.QColor('green'))
            self.table.setItem(row, 4, status_item)
    
    def export_csv(self):
        """Export history to CSV."""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export History", "", "CSV Files (*.csv)"
        )
        if filename:
            self.db.export_history_to_csv(filename)
            QtWidgets.QMessageBox.information(self, "Export Complete", "History exported to {}".format(filename))


