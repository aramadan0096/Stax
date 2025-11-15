# -*- coding: utf-8 -*-
"""
Pagination Widget
Provides pagination controls for large element lists
"""

from PySide2 import QtWidgets, QtCore
from src.icon_loader import get_icon


class PaginationWidget(QtWidgets.QWidget):
    """Pagination control widget for large element lists."""
    
    page_changed = QtCore.Signal(int)  # Emits current page number (0-indexed)
    
    def __init__(self, parent=None):
        super(PaginationWidget, self).__init__(parent)
        self.current_page = 0
        self.total_pages = 0
        self.items_per_page = 100
        self.total_items = 0
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup pagination UI."""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # First page button
        self.first_btn = QtWidgets.QPushButton()
        self.first_btn.setIcon(get_icon('previous', size=16))
        self.first_btn.setToolTip("First Page")
        self.first_btn.setMaximumWidth(40)
        self.first_btn.clicked.connect(lambda: self.go_to_page(0))
        layout.addWidget(self.first_btn)
        
        # Previous button
        self.prev_btn = QtWidgets.QPushButton()
        self.prev_btn.setIcon(get_icon('previous', size=16))
        self.prev_btn.setToolTip("Previous Page")
        self.prev_btn.setMaximumWidth(40)
        self.prev_btn.clicked.connect(self.previous_page)
        layout.addWidget(self.prev_btn)
        
        # Page info label
        self.page_label = QtWidgets.QLabel("Page 0 of 0")
        self.page_label.setAlignment(QtCore.Qt.AlignCenter)
        self.page_label.setMinimumWidth(150)
        layout.addWidget(self.page_label)
        
        # Next button
        self.next_btn = QtWidgets.QPushButton()
        self.next_btn.setIcon(get_icon('next', size=16))
        self.next_btn.setToolTip("Next Page")
        self.next_btn.setMaximumWidth(40)
        self.next_btn.clicked.connect(self.next_page)
        layout.addWidget(self.next_btn)
        
        # Last page button
        self.last_btn = QtWidgets.QPushButton()
        self.last_btn.setIcon(get_icon('next', size=16))
        self.last_btn.setToolTip("Last Page")
        self.last_btn.setMaximumWidth(40)
        self.last_btn.clicked.connect(lambda: self.go_to_page(self.total_pages - 1))
        layout.addWidget(self.last_btn)
        
        layout.addStretch()
        
        # Items per page selector
        layout.addWidget(QtWidgets.QLabel("Items per page:"))
        self.items_combo = QtWidgets.QComboBox()
        self.items_combo.addItems(['50', '100', '200', '500'])
        self.items_combo.setCurrentText('100')
        self.items_combo.currentTextChanged.connect(self.on_items_per_page_changed)
        layout.addWidget(self.items_combo)
        
        # Info label (showing X-Y of Z)
        self.info_label = QtWidgets.QLabel("")
        self.info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.info_label)
        
        self.update_buttons()
    
    def set_total_items(self, total):
        """Set total number of items and recalculate pages."""
        self.total_items = total
        self.total_pages = max(1, (total + self.items_per_page - 1) // self.items_per_page)
        
        # Reset to first page if current page is out of range
        if self.current_page >= self.total_pages:
            self.current_page = 0
        
        self.update_ui()
    
    def set_items_per_page(self, count):
        """Set items per page."""
        self.items_per_page = count
        self.items_combo.setCurrentText(str(count))
        self.set_total_items(self.total_items)  # Recalculate
    
    def on_items_per_page_changed(self, text):
        """Handle items per page change."""
        self.items_per_page = int(text)
        self.set_total_items(self.total_items)  # Recalculate
        self.page_changed.emit(self.current_page)
    
    def go_to_page(self, page):
        """Navigate to specific page."""
        if 0 <= page < self.total_pages and page != self.current_page:
            self.current_page = page
            self.update_ui()
            self.page_changed.emit(self.current_page)
    
    def next_page(self):
        """Go to next page."""
        if self.current_page < self.total_pages - 1:
            self.go_to_page(self.current_page + 1)
    
    def previous_page(self):
        """Go to previous page."""
        if self.current_page > 0:
            self.go_to_page(self.current_page - 1)
    
    def update_ui(self):
        """Update pagination UI elements."""
        if self.total_items == 0:
            self.page_label.setText("Page 0 of 0")
            self.info_label.setText("")
        else:
            self.page_label.setText("Page {} of {}".format(self.current_page + 1, self.total_pages))
            
            # Calculate item range
            start_item = self.current_page * self.items_per_page + 1
            end_item = min((self.current_page + 1) * self.items_per_page, self.total_items)
            self.info_label.setText("Showing {}-{} of {} items".format(start_item, end_item, self.total_items))
        
        self.update_buttons()
    
    def update_buttons(self):
        """Enable/disable buttons based on current page."""
        self.first_btn.setEnabled(self.current_page > 0)
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.total_pages - 1)
        self.last_btn.setEnabled(self.current_page < self.total_pages - 1)
    
    def get_page_slice(self):
        """Get (start, end) indices for current page."""
        start = self.current_page * self.items_per_page
        end = min(start + self.items_per_page, self.total_items)
        return start, end
