# -*- coding: utf-8 -*-
"""
Main GUI for VFX_Asset_Hub
PySide2-based user interface with drag-and-drop support
Python 2.7 compatible
"""

import os
import sys
from PySide2 import QtWidgets, QtCore, QtGui

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.config import Config
from src.db_manager import DatabaseManager
from src.ingestion_core import IngestionCore
from src.nuke_bridge import NukeBridge, NukeIntegration
from src.extensibility_hooks import ProcessorManager


class MediaInfoPopup(QtWidgets.QDialog):
    """
    Non-modal popup for displaying media information.
    Triggered by Alt+Hover over element.
    """
    
    # Signals
    insert_requested = QtCore.Signal(int)  # element_id
    reveal_requested = QtCore.Signal(str)  # filepath
    
    def __init__(self, parent=None):
        super(MediaInfoPopup, self).__init__(parent)
        self.element_data = None
        self.setWindowFlags(
            QtCore.Qt.Tool | 
            QtCore.Qt.FramelessWindowHint | 
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        self.setFixedSize(400, 550)
        
        # Main layout with border
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container with styling
        container = QtWidgets.QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border: 2px solid #555555;
                border-radius: 4px;
            }
        """)
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        self.title_label = QtWidgets.QLabel("Element Info")
        self.title_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #ffffff;
            border: none;
        """)
        container_layout.addWidget(self.title_label)
        
        # Preview image
        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setFixedSize(380, 280)
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            background-color: #1e1e1e;
            border: 1px solid #444444;
            color: #888888;
        """)
        self.preview_label.setText("No Preview")
        container_layout.addWidget(self.preview_label)
        
        # Metadata section
        metadata_widget = QtWidgets.QWidget()
        metadata_widget.setStyleSheet("border: none;")
        metadata_layout = QtWidgets.QFormLayout(metadata_widget)
        metadata_layout.setContentsMargins(0, 10, 0, 10)
        
        label_style = "color: #aaaaaa; border: none;"
        value_style = "color: #ffffff; border: none; font-weight: bold;"
        
        self.name_label = QtWidgets.QLabel()
        self.name_label.setStyleSheet(value_style)
        self.name_label.setWordWrap(True)
        metadata_layout.addRow(self._create_label("Name:", label_style), self.name_label)
        
        self.type_label = QtWidgets.QLabel()
        self.type_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Type:", label_style), self.type_label)
        
        self.format_label = QtWidgets.QLabel()
        self.format_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Format:", label_style), self.format_label)
        
        self.frames_label = QtWidgets.QLabel()
        self.frames_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Frames:", label_style), self.frames_label)
        
        self.size_label = QtWidgets.QLabel()
        self.size_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Size:", label_style), self.size_label)
        
        self.path_label = QtWidgets.QLabel()
        self.path_label.setStyleSheet(value_style)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        metadata_layout.addRow(self._create_label("Path:", label_style), self.path_label)
        
        self.comment_label = QtWidgets.QLabel()
        self.comment_label.setStyleSheet(value_style)
        self.comment_label.setWordWrap(True)
        metadata_layout.addRow(self._create_label("Comment:", label_style), self.comment_label)
        
        container_layout.addWidget(metadata_widget)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.insert_btn = QtWidgets.QPushButton("Insert into Nuke")
        self.insert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2868a6;
            }
        """)
        self.insert_btn.clicked.connect(self.on_insert_clicked)
        button_layout.addWidget(self.insert_btn)
        
        self.reveal_btn = QtWidgets.QPushButton("Reveal in Explorer")
        self.reveal_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a5a5a;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #6a6a6a;
            }
            QPushButton:pressed {
                background-color: #4a4a4a;
            }
        """)
        self.reveal_btn.clicked.connect(self.on_reveal_clicked)
        button_layout.addWidget(self.reveal_btn)
        
        container_layout.addLayout(button_layout)
        
        main_layout.addWidget(container)
    
    def _create_label(self, text, style):
        """Helper to create styled label."""
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(style)
        return label
    
    def show_element(self, element_data, position=None):
        """
        Show popup with element data.
        
        Args:
            element_data (dict): Element data from database
            position (QPoint): Optional position to show popup
        """
        self.element_data = element_data
        
        # Update title
        self.title_label.setText(element_data.get('name', 'Unknown'))
        
        # Update metadata
        self.name_label.setText(element_data.get('name', 'N/A'))
        self.type_label.setText(element_data.get('type', 'N/A'))
        self.format_label.setText(element_data.get('format', 'N/A') or 'N/A')
        self.frames_label.setText(element_data.get('frame_range', 'N/A') or 'N/A')
        
        # Format file size
        file_size = element_data.get('file_size', 0)
        if file_size:
            size_mb = file_size / (1024.0 * 1024.0)
            if size_mb < 1024:
                size_str = "{:.1f} MB".format(size_mb)
            else:
                size_str = "{:.2f} GB".format(size_mb / 1024.0)
        else:
            size_str = 'N/A'
        self.size_label.setText(size_str)
        
        # Show path
        filepath = element_data.get('filepath_hard') if element_data.get('is_hard_copy') else element_data.get('filepath_soft')
        self.path_label.setText(filepath or 'N/A')
        
        # Show comment
        comment = element_data.get('comment', '')
        self.comment_label.setText(comment or 'No comment')
        
        # Load preview
        preview_path = element_data.get('preview_path')
        if preview_path and os.path.exists(preview_path):
            pixmap = QtGui.QPixmap(preview_path)
            scaled_pixmap = pixmap.scaled(
                380, 280,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
        else:
            self.preview_label.clear()
            self.preview_label.setText("No Preview Available")
        
        # Position popup
        if position:
            # Offset to the right and down a bit from cursor
            self.move(position.x() + 20, position.y() + 20)
        
        # Show popup
        self.show()
        self.raise_()
    
    def on_insert_clicked(self):
        """Handle Insert button click."""
        if self.element_data:
            self.insert_requested.emit(self.element_data['element_id'])
            self.hide()
    
    def on_reveal_clicked(self):
        """Handle Reveal button click."""
        if self.element_data:
            filepath = self.element_data.get('filepath_hard') if self.element_data.get('is_hard_copy') else self.element_data.get('filepath_soft')
            if filepath:
                self.reveal_requested.emit(filepath)
    
    def mousePressEvent(self, event):
        """Close popup on click anywhere."""
        self.hide()


class AdvancedSearchDialog(QtWidgets.QDialog):
    """Advanced search dialog with property and match type selection."""
    
    def __init__(self, db_manager, parent=None):
        super(AdvancedSearchDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Advanced Search")
        self.setModal(False)  # Non-modal
        self.setup_ui()
        self.results = []
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Search criteria
        criteria_group = QtWidgets.QGroupBox("Search Criteria")
        criteria_layout = QtWidgets.QFormLayout()
        
        # Property selection
        self.property_combo = QtWidgets.QComboBox()
        self.property_combo.addItems(['name', 'format', 'type', 'comment', 'tags'])
        criteria_layout.addRow("Search Property:", self.property_combo)
        
        # Match type selection
        self.match_combo = QtWidgets.QComboBox()
        self.match_combo.addItems(['loose', 'strict'])
        self.match_combo.setCurrentText('loose')
        criteria_layout.addRow("Match Type:", self.match_combo)
        
        # Search text
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Enter search text...")
        self.search_edit.returnPressed.connect(self.perform_search)
        criteria_layout.addRow("Search Text:", self.search_edit)
        
        criteria_group.setLayout(criteria_layout)
        layout.addWidget(criteria_group)
        
        # Search button
        search_btn = QtWidgets.QPushButton("Search")
        search_btn.clicked.connect(self.perform_search)
        search_btn.setDefault(True)
        layout.addWidget(search_btn)
        
        # Results table
        results_label = QtWidgets.QLabel("Search Results:")
        results_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(results_label)
        
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(['Name', 'Type', 'Format', 'Frames', 'Comment'])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.results_table.itemDoubleClicked.connect(self.on_result_double_clicked)
        layout.addWidget(self.results_table)
        
        # Status label
        self.status_label = QtWidgets.QLabel("Enter search criteria and click Search")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        self.resize(700, 500)
    
    def perform_search(self):
        """Perform search based on criteria."""
        search_text = self.search_edit.text().strip()
        if not search_text:
            QtWidgets.QMessageBox.warning(self, "Empty Search", "Please enter search text.")
            return
        
        property_name = self.property_combo.currentText()
        match_type = self.match_combo.currentText()
        
        # Perform search
        self.results = self.db.search_elements(search_text, property_name, match_type)
        
        # Update results table
        self.results_table.setRowCount(len(self.results))
        for row, element in enumerate(self.results):
            self.results_table.setItem(row, 0, QtWidgets.QTableWidgetItem(element['name']))
            self.results_table.setItem(row, 1, QtWidgets.QTableWidgetItem(element['type']))
            self.results_table.setItem(row, 2, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.results_table.setItem(row, 3, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.results_table.setItem(row, 4, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            
            # Store element_id in first column
            self.results_table.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
        
        # Update status
        self.status_label.setText("Found {} results".format(len(self.results)))
        self.status_label.setStyleSheet("color: green;" if len(self.results) > 0 else "color: orange;")
    
    def on_result_double_clicked(self, item):
        """Handle double-click on result."""
        element_id = self.results_table.item(item.row(), 0).data(QtCore.Qt.UserRole)
        if element_id:
            # Emit signal or trigger action
            self.parent().on_advanced_search_result(element_id)


class MediaInfoPopup(QtWidgets.QDialog):
    """
    Non-modal popup for displaying media information.
    Triggered by Alt+Hover over element.
    """
    
    # Signals
    insert_requested = QtCore.Signal(int)  # element_id
    reveal_requested = QtCore.Signal(str)  # filepath
    
    def __init__(self, parent=None):
        super(MediaInfoPopup, self).__init__(parent)
        self.element_data = None
        self.setWindowFlags(
            QtCore.Qt.Tool | 
            QtCore.Qt.FramelessWindowHint | 
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        self.setFixedSize(400, 550)
        
        # Main layout with border
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container with styling
        container = QtWidgets.QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border: 2px solid #555555;
                border-radius: 4px;
            }
        """)
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(10, 10, 10, 10)
        
        # Title
        self.title_label = QtWidgets.QLabel("Element Info")
        self.title_label.setStyleSheet("""
            font-weight: bold; 
            font-size: 14px; 
            color: #ffffff;
            border: none;
        """)
        container_layout.addWidget(self.title_label)
        
        # Preview image
        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setFixedSize(380, 280)
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            background-color: #1e1e1e;
            border: 1px solid #444444;
            color: #888888;
        """)
        self.preview_label.setText("No Preview")
        container_layout.addWidget(self.preview_label)
        
        # Metadata section
        metadata_widget = QtWidgets.QWidget()
        metadata_widget.setStyleSheet("border: none;")
        metadata_layout = QtWidgets.QFormLayout(metadata_widget)
        metadata_layout.setContentsMargins(0, 10, 0, 10)
        
        label_style = "color: #aaaaaa; border: none;"
        value_style = "color: #ffffff; border: none; font-weight: bold;"
        
        self.name_label = QtWidgets.QLabel()
        self.name_label.setStyleSheet(value_style)
        self.name_label.setWordWrap(True)
        metadata_layout.addRow(self._create_label("Name:", label_style), self.name_label)
        
        self.type_label = QtWidgets.QLabel()
        self.type_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Type:", label_style), self.type_label)
        
        self.format_label = QtWidgets.QLabel()
        self.format_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Format:", label_style), self.format_label)
        
        self.frames_label = QtWidgets.QLabel()
        self.frames_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Frames:", label_style), self.frames_label)
        
        self.size_label = QtWidgets.QLabel()
        self.size_label.setStyleSheet(value_style)
        metadata_layout.addRow(self._create_label("Size:", label_style), self.size_label)
        
        self.path_label = QtWidgets.QLabel()
        self.path_label.setStyleSheet(value_style)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        metadata_layout.addRow(self._create_label("Path:", label_style), self.path_label)
        
        self.comment_label = QtWidgets.QLabel()
        self.comment_label.setStyleSheet(value_style)
        self.comment_label.setWordWrap(True)
        metadata_layout.addRow(self._create_label("Comment:", label_style), self.comment_label)
        
        container_layout.addWidget(metadata_widget)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.insert_btn = QtWidgets.QPushButton("Insert into Nuke")
        self.insert_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2868a6;
            }
        """)
        self.insert_btn.clicked.connect(self.on_insert_clicked)
        button_layout.addWidget(self.insert_btn)
        
        self.reveal_btn = QtWidgets.QPushButton("Reveal in Explorer")
        self.reveal_btn.setStyleSheet("""
            QPushButton {
                background-color: #5a5a5a;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #6a6a6a;
            }
            QPushButton:pressed {
                background-color: #4a4a4a;
            }
        """)
        self.reveal_btn.clicked.connect(self.on_reveal_clicked)
        button_layout.addWidget(self.reveal_btn)
        
        container_layout.addLayout(button_layout)
        
        main_layout.addWidget(container)
    
    def _create_label(self, text, style):
        """Helper to create styled label."""
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(style)
        return label
    
    def show_element(self, element_data, position=None):
        """
        Show popup with element data.
        
        Args:
            element_data (dict): Element data from database
            position (QPoint): Optional position to show popup
        """
        self.element_data = element_data
        
        # Update title
        self.title_label.setText(element_data.get('name', 'Unknown'))
        
        # Update metadata
        self.name_label.setText(element_data.get('name', 'N/A'))
        self.type_label.setText(element_data.get('type', 'N/A'))
        self.format_label.setText(element_data.get('format', 'N/A') or 'N/A')
        self.frames_label.setText(element_data.get('frame_range', 'N/A') or 'N/A')
        
        # Format file size
        file_size = element_data.get('file_size', 0)
        if file_size:
            size_mb = file_size / (1024.0 * 1024.0)
            if size_mb < 1024:
                size_str = "{:.1f} MB".format(size_mb)
            else:
                size_str = "{:.2f} GB".format(size_mb / 1024.0)
        else:
            size_str = 'N/A'
        self.size_label.setText(size_str)
        
        # Show path
        filepath = element_data.get('filepath_hard') if element_data.get('is_hard_copy') else element_data.get('filepath_soft')
        self.path_label.setText(filepath or 'N/A')
        
        # Show comment
        comment = element_data.get('comment', '')
        self.comment_label.setText(comment or 'No comment')
        
        # Load preview
        preview_path = element_data.get('preview_path')
        if preview_path and os.path.exists(preview_path):
            pixmap = QtGui.QPixmap(preview_path)
            scaled_pixmap = pixmap.scaled(
                380, 280,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled_pixmap)
        else:
            self.preview_label.clear()
            self.preview_label.setText("No Preview Available")
        
        # Position popup
        if position:
            # Offset to the right and down a bit from cursor
            self.move(position.x() + 20, position.y() + 20)
        
        # Show popup
        self.show()
        self.raise_()
    
    def on_insert_clicked(self):
        """Handle Insert button click."""
        if self.element_data:
            self.insert_requested.emit(self.element_data['element_id'])
            self.hide()
    
    def on_reveal_clicked(self):
        """Handle Reveal button click."""
        if self.element_data:
            filepath = self.element_data.get('filepath_hard') if self.element_data.get('is_hard_copy') else self.element_data.get('filepath_soft')
            if filepath:
                self.reveal_requested.emit(filepath)
    
    def mousePressEvent(self, event):
        """Close popup on click anywhere."""
        self.hide()


class StacksListsPanel(QtWidgets.QWidget):
    """Left sidebar panel for Stacks and Lists navigation."""
    
    # Signals
    stack_selected = QtCore.Signal(int)  # stack_id
    list_selected = QtCore.Signal(int)   # list_id
    
    def __init__(self, db_manager, parent=None):
        super(StacksListsPanel, self).__init__(parent)
        self.db = db_manager
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup the UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QtWidgets.QLabel("Stacks & Lists")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        layout.addWidget(title)
        
        # Tree widget
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.tree)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.add_stack_btn = QtWidgets.QPushButton("+ Stack")
        self.add_stack_btn.clicked.connect(self.add_stack)
        button_layout.addWidget(self.add_stack_btn)
        
        self.add_list_btn = QtWidgets.QPushButton("+ List")
        self.add_list_btn.clicked.connect(self.add_list)
        button_layout.addWidget(self.add_list_btn)
        
        layout.addLayout(button_layout)
    
    def load_data(self):
        """Load stacks and lists from database."""
        self.tree.clear()
        
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            stack_item = QtWidgets.QTreeWidgetItem([stack['name']])
            stack_item.setData(0, QtCore.Qt.UserRole, ('stack', stack['stack_id']))
            stack_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
            self.tree.addTopLevelItem(stack_item)
            
            # Load lists for this stack
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                list_item = QtWidgets.QTreeWidgetItem([lst['name']])
                list_item.setData(0, QtCore.Qt.UserRole, ('list', lst['list_id']))
                list_item.setIcon(0, self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                stack_item.addChild(list_item)
            
            stack_item.setExpanded(True)
    
    def on_item_clicked(self, item, column):
        """Handle item click."""
        data = item.data(0, QtCore.Qt.UserRole)
        if data:
            item_type, item_id = data
            if item_type == 'stack':
                self.stack_selected.emit(item_id)
            elif item_type == 'list':
                self.list_selected.emit(item_id)
    
    def add_stack(self):
        """Add new stack dialog."""
        dialog = AddStackDialog(self.db, self)
        if dialog.exec_():
            self.load_data()
    
    def add_list(self):
        """Add new list dialog."""
        # Get selected stack
        current_item = self.tree.currentItem()
        stack_id = None
        
        if current_item:
            data = current_item.data(0, QtCore.Qt.UserRole)
            if data:
                item_type, item_id = data
                if item_type == 'stack':
                    stack_id = item_id
                elif item_type == 'list':
                    # Get parent stack
                    parent = current_item.parent()
                    if parent:
                        parent_data = parent.data(0, QtCore.Qt.UserRole)
                        if parent_data:
                            stack_id = parent_data[1]
        
        dialog = AddListDialog(self.db, stack_id, self)
        if dialog.exec_():
            self.load_data()


class MediaDisplayWidget(QtWidgets.QWidget):
    """Central widget for displaying media elements."""
    
    # Signals
    element_selected = QtCore.Signal(int)  # element_id
    element_double_clicked = QtCore.Signal(int)  # element_id
    
    def __init__(self, db_manager, config, parent=None):
        super(MediaDisplayWidget, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.current_list_id = None
        self.view_mode = 'gallery'  # 'gallery' or 'list'
        self.alt_pressed = False  # Track Alt key state
        self.hover_timer = QtCore.QTimer()
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.show_info_popup)
        self.hover_item = None
        self.media_popup = MediaInfoPopup(self)
        self.media_popup.insert_requested.connect(self.on_popup_insert)
        self.media_popup.reveal_requested.connect(self.on_popup_reveal)
        self.setup_ui()
        
        # Enable mouse tracking for hover events
        self.setMouseTracking(True)
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        
        # Search bar
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search elements...")
        self.search_box.textChanged.connect(self.on_search)
        toolbar.addWidget(self.search_box)
        
        # View mode toggle
        self.gallery_btn = QtWidgets.QPushButton("Gallery")
        self.gallery_btn.setCheckable(True)
        self.gallery_btn.setChecked(True)
        self.gallery_btn.clicked.connect(lambda: self.set_view_mode('gallery'))
        toolbar.addWidget(self.gallery_btn)
        
        self.list_btn = QtWidgets.QPushButton("List")
        self.list_btn.setCheckable(True)
        self.list_btn.clicked.connect(lambda: self.set_view_mode('list'))
        toolbar.addWidget(self.list_btn)
        
        # Element size slider
        self.size_label = QtWidgets.QLabel("Size:")
        toolbar.addWidget(self.size_label)
        
        self.size_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.size_slider.setMinimum(64)
        self.size_slider.setMaximum(512)
        self.size_slider.setValue(256)
        self.size_slider.setMaximumWidth(150)
        self.size_slider.valueChanged.connect(self.on_size_changed)
        toolbar.addWidget(self.size_slider)
        
        layout.addLayout(toolbar)
        
        # Stacked widget for different views
        self.view_stack = QtWidgets.QStackedWidget()
        
        # Gallery view (grid of thumbnails)
        self.gallery_view = QtWidgets.QListWidget()
        self.gallery_view.setViewMode(QtWidgets.QListView.IconMode)
        self.gallery_view.setResizeMode(QtWidgets.QListView.Adjust)
        self.gallery_view.setIconSize(QtCore.QSize(256, 256))
        self.gallery_view.setSpacing(10)
        self.gallery_view.setDragEnabled(True)
        self.gallery_view.itemClicked.connect(self.on_item_clicked)
        self.gallery_view.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.gallery_view.setMouseTracking(True)  # Enable hover tracking
        self.gallery_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.gallery_view)
        
        # List view (table)
        self.table_view = QtWidgets.QTableWidget()
        self.table_view.setColumnCount(6)
        self.table_view.setHorizontalHeaderLabels(['Name', 'Format', 'Frames', 'Type', 'Size', 'Comment'])
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table_view.itemClicked.connect(self.on_table_item_clicked)
        self.table_view.itemDoubleClicked.connect(self.on_table_item_double_clicked)
        self.table_view.setMouseTracking(True)  # Enable hover tracking
        self.table_view.viewport().installEventFilter(self)  # Install event filter
        self.view_stack.addWidget(self.table_view)
        
        layout.addWidget(self.view_stack)
        
        # Info label
        self.info_label = QtWidgets.QLabel("Select a list to view elements")
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("color: gray; font-size: 12px; padding: 20px;")
        layout.addWidget(self.info_label)
    
    def set_view_mode(self, mode):
        """Switch between gallery and list view."""
        self.view_mode = mode
        
        if mode == 'gallery':
            self.view_stack.setCurrentWidget(self.gallery_view)
            self.gallery_btn.setChecked(True)
            self.list_btn.setChecked(False)
            self.size_slider.setEnabled(True)
        else:
            self.view_stack.setCurrentWidget(self.table_view)
            self.list_btn.setChecked(True)
            self.gallery_btn.setChecked(False)
            self.size_slider.setEnabled(False)
    
    def on_size_changed(self, value):
        """Handle thumbnail size change."""
        self.gallery_view.setIconSize(QtCore.QSize(value, value))
    
    def load_elements(self, list_id):
        """Load elements for a list."""
        self.current_list_id = list_id
        elements = self.db.get_elements_by_list(list_id)
        
        self.info_label.setVisible(len(elements) == 0)
        
        if len(elements) > 0:
            self.info_label.setText("")
        else:
            lst = self.db.get_list_by_id(list_id)
            if lst:
                self.info_label.setText("No elements in '{}'".format(lst['name']))
        
        # Update gallery view
        self.gallery_view.clear()
        for element in elements:
            item = QtWidgets.QListWidgetItem()
            item.setText(element['name'])
            item.setData(QtCore.Qt.UserRole, element['element_id'])
            
            # Load preview if available
            if element['preview_path'] and os.path.exists(element['preview_path']):
                pixmap = QtGui.QPixmap(element['preview_path'])
                item.setIcon(QtGui.QIcon(pixmap))
            else:
                # Default icon based on type
                if element['type'] == '2D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                elif element['type'] == '3D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
                else:
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
            
            self.gallery_view.addItem(item)
        
        # Update table view
        self.table_view.setRowCount(len(elements))
        for row, element in enumerate(elements):
            self.table_view.setItem(row, 0, QtWidgets.QTableWidgetItem(element['name']))
            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element['type']))
            
            # Format file size
            size_str = ''
            if element['file_size']:
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
            
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            
            # Store element_id in first column
            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
    
    def on_search(self, text):
        """Handle search text change (live filter)."""
        if not self.current_list_id:
            return
        
        # Get all elements
        elements = self.db.get_elements_by_list(self.current_list_id)
        
        # Filter by search text
        if text:
            filtered = [e for e in elements if text.lower() in e['name'].lower()]
        else:
            filtered = elements
        
        # Update gallery view
        self.gallery_view.clear()
        for element in filtered:
            item = QtWidgets.QListWidgetItem()
            item.setText(element['name'])
            item.setData(QtCore.Qt.UserRole, element['element_id'])
            
            if element['preview_path'] and os.path.exists(element['preview_path']):
                pixmap = QtGui.QPixmap(element['preview_path'])
                item.setIcon(QtGui.QIcon(pixmap))
            else:
                if element['type'] == '2D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon))
                elif element['type'] == '3D':
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DriveFDIcon))
                else:
                    item.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
            
            self.gallery_view.addItem(item)
        
        # Update table view
        self.table_view.setRowCount(len(filtered))
        for row, element in enumerate(filtered):
            self.table_view.setItem(row, 0, QtWidgets.QTableWidgetItem(element['name']))
            self.table_view.setItem(row, 1, QtWidgets.QTableWidgetItem(element['format'] or ''))
            self.table_view.setItem(row, 2, QtWidgets.QTableWidgetItem(element['frame_range'] or ''))
            self.table_view.setItem(row, 3, QtWidgets.QTableWidgetItem(element['type']))
            
            size_str = ''
            if element['file_size']:
                size_mb = element['file_size'] / (1024.0 * 1024.0)
                if size_mb < 1024:
                    size_str = "{:.1f} MB".format(size_mb)
                else:
                    size_str = "{:.2f} GB".format(size_mb / 1024.0)
            self.table_view.setItem(row, 4, QtWidgets.QTableWidgetItem(size_str))
            
            self.table_view.setItem(row, 5, QtWidgets.QTableWidgetItem(element['comment'] or ''))
            self.table_view.item(row, 0).setData(QtCore.Qt.UserRole, element['element_id'])
    
    def on_item_clicked(self, item):
        """Handle gallery item click."""
        element_id = item.data(QtCore.Qt.UserRole)
        self.element_selected.emit(element_id)
    
    def on_item_double_clicked(self, item):
        """Handle gallery item double-click."""
        element_id = item.data(QtCore.Qt.UserRole)
        self.element_double_clicked.emit(element_id)
    
    def on_table_item_clicked(self, item):
        """Handle table item click."""
        element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
        self.element_selected.emit(element_id)
    
    def on_table_item_double_clicked(self, item):
        """Handle table item double-click."""
        element_id = self.table_view.item(item.row(), 0).data(QtCore.Qt.UserRole)
        self.element_double_clicked.emit(element_id)
    
    def eventFilter(self, obj, event):
        """Event filter to handle Alt+Hover."""
        # Check if widgets are initialized
        if not hasattr(self, 'gallery_view') or not hasattr(self, 'table_view'):
            return super(MediaDisplayWidget, self).eventFilter(obj, event)
        
        if obj in [self.gallery_view.viewport(), self.table_view.viewport()]:
            if event.type() == QtCore.QEvent.MouseMove:
                # Check if Alt is pressed
                modifiers = QtWidgets.QApplication.keyboardModifiers()
                self.alt_pressed = (modifiers & QtCore.Qt.AltModifier)
                
                if self.alt_pressed:
                    # Get item under cursor
                    pos = event.pos()
                    
                    if obj == self.gallery_view.viewport():
                        item = self.gallery_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                    elif obj == self.table_view.viewport():
                        item = self.table_view.itemAt(pos)
                        if item and item != self.hover_item:
                            self.hover_item = item
                            self.hover_timer.stop()
                            self.hover_timer.start(500)  # 500ms delay
                else:
                    # Hide popup if Alt released
                    if self.media_popup.isVisible():
                        self.media_popup.hide()
                    self.hover_timer.stop()
                    self.hover_item = None
            
            elif event.type() == QtCore.QEvent.Leave:
                # Hide popup when leaving widget
                self.hover_timer.stop()
                self.hover_item = None
        
        return super(MediaDisplayWidget, self).eventFilter(obj, event)
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == QtCore.Qt.Key_Alt:
            self.alt_pressed = True
        super(MediaDisplayWidget, self).keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """Handle key release events."""
        if event.key() == QtCore.Qt.Key_Alt:
            self.alt_pressed = False
            if self.media_popup.isVisible():
                self.media_popup.hide()
            self.hover_timer.stop()
        super(MediaDisplayWidget, self).keyReleaseEvent(event)
    
    def show_info_popup(self):
        """Show media info popup for hovered item."""
        if not self.hover_item or not self.alt_pressed:
            return
        
        # Get element ID from item
        element_id = None
        
        if self.view_mode == 'gallery':
            element_id = self.hover_item.data(QtCore.Qt.UserRole)
        else:  # list view
            element_id = self.table_view.item(self.hover_item.row(), 0).data(QtCore.Qt.UserRole)
        
        if element_id:
            element_data = self.db.get_element_by_id(element_id)
            if element_data:
                # Get global cursor position
                cursor_pos = QtGui.QCursor.pos()
                self.media_popup.show_element(element_data, cursor_pos)
    
    def on_popup_insert(self, element_id):
        """Handle insert request from popup."""
        self.element_double_clicked.emit(element_id)
    
    def on_popup_reveal(self, filepath):
        """Handle reveal request from popup."""
        if filepath and os.path.exists(filepath):
            # Reveal in file explorer
            import subprocess
            import platform
            
            # Get directory path
            if os.path.isfile(filepath):
                directory = os.path.dirname(filepath)
            else:
                directory = filepath
            
            # Open in OS file explorer
            if platform.system() == 'Windows':
                subprocess.Popen(['explorer', '/select,', os.path.normpath(filepath)])
            elif platform.system() == 'Darwin':  # macOS
                subprocess.Popen(['open', '-R', filepath])
            else:  # Linux
                subprocess.Popen(['xdg-open', directory])


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


class SettingsPanel(QtWidgets.QWidget):
    """Panel for application settings."""
    
    settings_changed = QtCore.Signal()
    
    def __init__(self, config, parent=None):
        super(SettingsPanel, self).__init__(parent)
        self.config = config
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title = QtWidgets.QLabel("Settings")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Scroll area for settings
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QFormLayout(scroll_widget)
        
        # Ingestion settings
        group1 = QtWidgets.QGroupBox("Ingestion Settings")
        group1_layout = QtWidgets.QFormLayout()
        
        self.copy_policy = QtWidgets.QComboBox()
        self.copy_policy.addItems(['soft', 'hard'])
        self.copy_policy.setCurrentText(self.config.get('default_copy_policy'))
        group1_layout.addRow("Default Copy Policy:", self.copy_policy)
        
        self.auto_detect = QtWidgets.QCheckBox()
        self.auto_detect.setChecked(self.config.get('auto_detect_sequences'))
        group1_layout.addRow("Auto-detect Sequences:", self.auto_detect)
        
        self.gen_previews = QtWidgets.QCheckBox()
        self.gen_previews.setChecked(self.config.get('generate_previews'))
        group1_layout.addRow("Generate Previews:", self.gen_previews)
        
        group1.setLayout(group1_layout)
        scroll_layout.addRow(group1)
        
        # Processor hooks
        group2 = QtWidgets.QGroupBox("Custom Processors")
        group2_layout = QtWidgets.QFormLayout()
        
        self.pre_ingest = QtWidgets.QLineEdit(self.config.get('pre_ingest_processor') or '')
        pre_ingest_browse = QtWidgets.QPushButton("Browse...")
        pre_ingest_browse.clicked.connect(lambda: self.browse_file(self.pre_ingest))
        pre_layout = QtWidgets.QHBoxLayout()
        pre_layout.addWidget(self.pre_ingest)
        pre_layout.addWidget(pre_ingest_browse)
        group2_layout.addRow("Pre-Ingest Hook:", pre_layout)
        
        self.post_ingest = QtWidgets.QLineEdit(self.config.get('post_ingest_processor') or '')
        post_ingest_browse = QtWidgets.QPushButton("Browse...")
        post_ingest_browse.clicked.connect(lambda: self.browse_file(self.post_ingest))
        post_layout = QtWidgets.QHBoxLayout()
        post_layout.addWidget(self.post_ingest)
        post_layout.addWidget(post_ingest_browse)
        group2_layout.addRow("Post-Ingest Hook:", post_layout)
        
        self.post_import = QtWidgets.QLineEdit(self.config.get('post_import_processor') or '')
        post_import_browse = QtWidgets.QPushButton("Browse...")
        post_import_browse.clicked.connect(lambda: self.browse_file(self.post_import))
        import_layout = QtWidgets.QHBoxLayout()
        import_layout.addWidget(self.post_import)
        import_layout.addWidget(post_import_browse)
        group2_layout.addRow("Post-Import Hook:", import_layout)
        
        group2.setLayout(group2_layout)
        scroll_layout.addRow(group2)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(save_btn)
        
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
    
    def browse_file(self, line_edit):
        """Browse for processor script file."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Processor Script", "", "Python Files (*.py)"
        )
        if filename:
            line_edit.setText(filename)
    
    def save_settings(self):
        """Save settings to config."""
        self.config.set('default_copy_policy', self.copy_policy.currentText())
        self.config.set('auto_detect_sequences', self.auto_detect.isChecked())
        self.config.set('generate_previews', self.gen_previews.isChecked())
        self.config.set('pre_ingest_processor', self.pre_ingest.text() or None)
        self.config.set('post_ingest_processor', self.post_ingest.text() or None)
        self.config.set('post_import_processor', self.post_import.text() or None)
        
        QtWidgets.QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
        self.settings_changed.emit()
    
    def reset_settings(self):
        """Reset settings to defaults."""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.config.reset_to_defaults()
            self.setup_ui()  # Reload UI
            QtWidgets.QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            self.settings_changed.emit()


class AddStackDialog(QtWidgets.QDialog):
    """Dialog for adding a new stack."""
    
    def __init__(self, db_manager, parent=None):
        super(AddStackDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Add Stack")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("Stack Name:", self.name_edit)
        
        path_layout = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        path_layout.addWidget(self.path_edit)
        
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(browse_btn)
        
        layout.addRow("Repository Path:", path_layout)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def browse_path(self):
        """Browse for repository path."""
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Repository Path")
        if path:
            self.path_edit.setText(path)
    
    def accept(self):
        """Validate and create stack."""
        name = self.name_edit.text().strip()
        path = self.path_edit.text().strip()
        
        if not name or not path:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide both name and path.")
            return
        
        try:
            self.db.create_stack(name, path)
            super(AddStackDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create stack: {}".format(str(e)))


class AddListDialog(QtWidgets.QDialog):
    """Dialog for adding a new list."""
    
    def __init__(self, db_manager, default_stack_id=None, parent=None):
        super(AddListDialog, self).__init__(parent)
        self.db = db_manager
        self.default_stack_id = default_stack_id
        self.setWindowTitle("Add List")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        # Stack selection
        self.stack_combo = QtWidgets.QComboBox()
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            self.stack_combo.addItem(stack['name'], stack['stack_id'])
        
        if self.default_stack_id:
            index = self.stack_combo.findData(self.default_stack_id)
            if index >= 0:
                self.stack_combo.setCurrentIndex(index)
        
        layout.addRow("Parent Stack:", self.stack_combo)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("List Name:", self.name_edit)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        """Validate and create list."""
        name = self.name_edit.text().strip()
        stack_id = self.stack_combo.currentData()
        
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide a list name.")
            return
        
        try:
            self.db.create_list(stack_id, name)
            super(AddListDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create list: {}".format(str(e)))


class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        # Initialize core components
        self.config = Config()
        self.config.ensure_directories()
        
        self.db = DatabaseManager(self.config.get('database_path'))
        self.nuke_bridge = NukeBridge(mock_mode=self.config.get('nuke_mock_mode'))
        self.nuke_integration = NukeIntegration(self.nuke_bridge, self.db)
        self.ingestion = IngestionCore(self.db, self.config.get_all())
        self.processor_manager = ProcessorManager(self.config.get_all())
        
        self.setWindowTitle("VFX Asset Hub")
        self.resize(1400, 800)
        
        self.setup_ui()
        self.setup_shortcuts()
    
    def setup_ui(self):
        """Setup the main window UI."""
        # Central widget
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Splitter for main content
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        
        # Left: Stacks/Lists panel
        self.stacks_panel = StacksListsPanel(self.db)
        self.stacks_panel.list_selected.connect(self.on_list_selected)
        main_splitter.addWidget(self.stacks_panel)
        
        # Center: Media display
        self.media_display = MediaDisplayWidget(self.db, self.config)
        self.media_display.element_double_clicked.connect(self.on_element_double_clicked)
        main_splitter.addWidget(self.media_display)
        
        # Set splitter sizes
        main_splitter.setSizes([250, 1150])
        
        layout.addWidget(main_splitter)
        
        # Create dockable panels
        
        # History panel (dockable)
        self.history_dock = QtWidgets.QDockWidget("History", self)
        self.history_panel = HistoryPanel(self.db)
        self.history_dock.setWidget(self.history_panel)
        self.history_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.BottomDockWidgetArea, self.history_dock)
        
        # Settings panel (dockable)
        self.settings_dock = QtWidgets.QDockWidget("Settings", self)
        self.settings_panel = SettingsPanel(self.config)
        self.settings_panel.settings_changed.connect(self.on_settings_changed)
        self.settings_dock.setWidget(self.settings_panel)
        self.settings_dock.setVisible(False)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.settings_dock)
        
        # Menu bar
        self.create_menus()
        
        # Status bar
        self.statusBar().showMessage("Ready")
    
    def create_menus(self):
        """Create menu bar."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        ingest_action = QtWidgets.QAction("Ingest Files...", self)
        ingest_action.setShortcut("Ctrl+I")
        ingest_action.triggered.connect(self.ingest_files)
        file_menu.addAction(ingest_action)
        
        file_menu.addSeparator()
        
        exit_action = QtWidgets.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Search menu
        search_menu = menubar.addMenu("Search")
        
        advanced_search_action = QtWidgets.QAction("Advanced Search...", self)
        advanced_search_action.setShortcut("Ctrl+F")
        advanced_search_action.triggered.connect(self.show_advanced_search)
        search_menu.addAction(advanced_search_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        history_action = QtWidgets.QAction("History Panel", self)
        history_action.setShortcut("Ctrl+2")
        history_action.setCheckable(True)
        history_action.triggered.connect(self.toggle_history)
        view_menu.addAction(history_action)
        
        settings_action = QtWidgets.QAction("Settings Panel", self)
        settings_action.setShortcut("Ctrl+3")
        settings_action.setCheckable(True)
        settings_action.triggered.connect(self.toggle_settings)
        view_menu.addAction(settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QtWidgets.QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Ctrl+2 for history
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+2"), self, self.toggle_history)
        
        # Ctrl+3 for settings
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+3"), self, self.toggle_settings)
    
    def toggle_history(self):
        """Toggle history panel visibility."""
        visible = not self.history_dock.isVisible()
        self.history_dock.setVisible(visible)
        if visible:
            self.history_panel.load_history()
    
    def toggle_settings(self):
        """Toggle settings panel visibility."""
        self.settings_dock.setVisible(not self.settings_dock.isVisible())
    
    def on_list_selected(self, list_id):
        """Handle list selection."""
        self.media_display.load_elements(list_id)
        
        lst = self.db.get_list_by_id(list_id)
        if lst:
            stack = self.db.get_stack_by_id(lst['stack_fk'])
            if stack:
                self.statusBar().showMessage("Viewing: {} > {}".format(stack['name'], lst['name']))
    
    def on_element_double_clicked(self, element_id):
        """Handle element double-click (insert into Nuke)."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted: {}".format(element['name']))
                QtWidgets.QMessageBox.information(
                    self,
                    "Element Inserted",
                    "Element '{}' has been inserted into Nuke.".format(element['name'])
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def ingest_files(self):
        """Open file dialog to ingest files."""
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Files to Ingest", "", "All Files (*.*)"
        )
        
        if not files:
            return
        
        # Ask for target list
        dialog = SelectListDialog(self.db, self)
        if dialog.exec_():
            target_list_id = dialog.get_selected_list()
            if target_list_id:
                self.perform_ingestion(files, target_list_id)
    
    def perform_ingestion(self, files, target_list_id):
        """Perform ingestion of files."""
        progress = QtWidgets.QProgressDialog("Ingesting files...", "Cancel", 0, len(files), self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        
        success_count = 0
        error_count = 0
        
        for i, filepath in enumerate(files):
            if progress.wasCanceled():
                break
            
            progress.setValue(i)
            progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
            
            result = self.ingestion.ingest_file(
                filepath,
                target_list_id,
                copy_policy=self.config.get('default_copy_policy')
            )
            
            if result['success']:
                success_count += 1
            else:
                error_count += 1
        
        progress.setValue(len(files))
        
        # Show result
        QtWidgets.QMessageBox.information(
            self,
            "Ingestion Complete",
            "Ingested {} files successfully.\n{} errors.".format(success_count, error_count)
        )
        
        # Refresh current view
        if self.media_display.current_list_id:
            self.media_display.load_elements(self.media_display.current_list_id)
    
    def on_settings_changed(self):
        """Handle settings change."""
        # Reload processor manager
        self.processor_manager = ProcessorManager(self.config.get_all())
        self.statusBar().showMessage("Settings updated")
    
    def show_advanced_search(self):
        """Show advanced search dialog."""
        if not hasattr(self, 'advanced_search_dialog') or self.advanced_search_dialog is None:
            self.advanced_search_dialog = AdvancedSearchDialog(self.db, self)
        self.advanced_search_dialog.show()
        self.advanced_search_dialog.raise_()
    
    def on_advanced_search_result(self, element_id):
        """Handle result selection from advanced search."""
        try:
            self.nuke_integration.insert_element(element_id)
            element = self.db.get_element_by_id(element_id)
            if element:
                self.statusBar().showMessage("Inserted from search: {}".format(element['name']))
                QtWidgets.QMessageBox.information(
                    self,
                    "Element Inserted",
                    "Element '{}' has been inserted into Nuke.".format(element['name'])
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to insert element: {}".format(str(e)))
    
    def show_about(self):
        """Show about dialog."""
        QtWidgets.QMessageBox.about(
            self,
            "About VFX Asset Hub",
            "<h3>VFX Asset Hub</h3>"
            "<p>Version 0.1.0 (Alpha)</p>"
            "<p>Professional VFX asset management pipeline.</p>"
            "<p>Python 2.7 | PySide2</p>"
        )


class SelectListDialog(QtWidgets.QDialog):
    """Dialog for selecting a target list for ingestion."""
    
    def __init__(self, db_manager, parent=None):
        super(SelectListDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Select Target List")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("Select target list for ingestion:")
        layout.addWidget(label)
        
        # Tree widget showing stacks and lists
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)
        
        # Load data
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            stack_item = QtWidgets.QTreeWidgetItem([stack['name']])
            stack_item.setData(0, QtCore.Qt.UserRole, ('stack', stack['stack_id']))
            stack_item.setFlags(stack_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(stack_item)
            
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                list_item = QtWidgets.QTreeWidgetItem([lst['name']])
                list_item.setData(0, QtCore.Qt.UserRole, ('list', lst['list_id']))
                stack_item.addChild(list_item)
            
            stack_item.setExpanded(True)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_selected_list(self):
        """Get selected list ID."""
        current = self.tree.currentItem()
        if current:
            data = current.data(0, QtCore.Qt.UserRole)
            if data and data[0] == 'list':
                return data[1]
        return None


def main():
    """Main entry point."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
