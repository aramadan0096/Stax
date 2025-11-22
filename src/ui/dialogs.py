# -*- coding: utf-8 -*-
"""
Dialog Widgets
Collection of dialog classes for StaX application
"""

import os
import sys
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon


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
        search_btn.setIcon(get_icon('search', size=20))
        search_btn.setObjectName('primary')
        search_btn.setProperty('class', 'primary')
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
        close_btn.setObjectName('small')
        close_btn.setProperty('class', 'small')
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
        browse_btn.setObjectName('small')
        browse_btn.setProperty('class', 'small')
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




class AddSubListDialog(QtWidgets.QDialog):
    """Dialog for adding a sub-list under a parent list."""
    
    def __init__(self, db_manager, parent_list_id, stack_id, parent=None):
        super(AddSubListDialog, self).__init__(parent)
        self.db = db_manager
        self.parent_list_id = parent_list_id
        self.stack_id = stack_id
        self.setWindowTitle("Add Sub-List")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        # Show parent list info
        parent_list = self.db.get_list_by_id(self.parent_list_id)
        if parent_list:
            parent_label = QtWidgets.QLabel(parent_list['name'])
            parent_label.setStyleSheet("font-weight: bold; color: #16c6b0;")
            layout.addRow("Parent List:", parent_label)
        
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g., 'Aerial Explosions'")
        layout.addRow("Sub-List Name:", self.name_edit)
        
        # Info label
        info_label = QtWidgets.QLabel("This sub-list will be nested under the parent list.")
        info_label.setStyleSheet("color: #888888; font-style: italic; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addRow("", info_label)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        """Validate and create sub-list."""
        name = self.name_edit.text().strip()
        
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide a sub-list name.")
            return
        
        try:
            self.db.create_list(self.stack_id, name, parent_list_id=self.parent_list_id)
            QtWidgets.QMessageBox.information(self, "Success", "Sub-list '{}' created successfully!".format(name))
            super(AddSubListDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create sub-list: {}".format(str(e)))




class CreatePlaylistDialog(QtWidgets.QDialog):
    """Dialog for creating a new playlist."""
    
    def __init__(self, db_manager, config, parent=None):
        super(CreatePlaylistDialog, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.setWindowTitle("Create Playlist")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QFormLayout(self)
        
        self.name_edit = QtWidgets.QLineEdit()
        layout.addRow("Playlist Name:", self.name_edit)
        
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText("Optional description...")
        layout.addRow("Description:", self.desc_edit)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)
    
    def accept(self):
        """Validate and create playlist."""
        name = self.name_edit.text().strip()
        description = self.desc_edit.toPlainText().strip()
        
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please provide a playlist name.")
            return
        
        try:
            self.db.create_playlist(
                name,
                description,
                self.config.get('user_name'),
                self.config.get('machine_name')
            )
            super(CreatePlaylistDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to create playlist: {}".format(str(e)))




class AddToPlaylistDialog(QtWidgets.QDialog):
    """Dialog for adding element to playlist."""
    
    def __init__(self, db_manager, element_id, parent=None):
        super(AddToPlaylistDialog, self).__init__(parent)
        self.db = db_manager
        self.element_id = element_id
        self.setWindowTitle("Add to Playlist")
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("Select playlist to add element:")
        layout.addWidget(label)
        
        # List of playlists
        self.playlist_list = QtWidgets.QListWidget()
        playlists = self.db.get_all_playlists()
        
        for playlist in playlists:
            # Check if element already in playlist
            is_in = self.db.is_element_in_playlist(playlist['playlist_id'], self.element_id)
            
            item = QtWidgets.QListWidgetItem()
            if is_in:
                item.setText("[Added] " + playlist['name'] + " (already added)")
                item.setForeground(QtGui.QColor('gray'))
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled)
            else:
                item.setText(playlist['name'])
            
            item.setData(QtCore.Qt.UserRole, playlist['playlist_id'])
            self.playlist_list.addItem(item)
        
        layout.addWidget(self.playlist_list)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def accept(self):
        """Add element to selected playlist."""
        current = self.playlist_list.currentItem()
        if not current:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a playlist.")
            return
        
        playlist_id = current.data(QtCore.Qt.UserRole)
        
        try:
            result = self.db.add_element_to_playlist(playlist_id, self.element_id)
            if result is None:
                QtWidgets.QMessageBox.information(self, "Already Added", "Element is already in this playlist.")
            else:
                super(AddToPlaylistDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to add element: {}".format(str(e)))




class LoginDialog(QtWidgets.QDialog):
    """Login dialog for user authentication."""
    
    def __init__(self, db_manager, parent=None):
        super(LoginDialog, self).__init__(parent)
        self.db = db_manager
        self.authenticated_user = None
        
        self.setWindowTitle("Stax - Login")
        self.setModal(True)
        self.setFixedSize(500, 350)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 20, 30, 20)
        
        # Logo/Title
        title_label = QtWidgets.QLabel("Stax")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #16c6b0; padding: 10px;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title_label)
        
        subtitle_label = QtWidgets.QLabel("Please login to continue")
        subtitle_label.setStyleSheet("color: #888888; font-size: 12px;")
        subtitle_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(subtitle_label)
        
        layout.addSpacing(10)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        # Increased spacing between fields
        form.setSpacing(25)
        form.setContentsMargins(0, 0, 0, 0)
        try:
            # setVerticalSpacing may not exist in older Qt versions; guard it
            form.setVerticalSpacing(25)
        except Exception:
            pass
        
        # Username
        self.username_edit = QtWidgets.QLineEdit()
        self.username_edit.setPlaceholderText("Enter username")
        # larger control for accessibility / spacing
        self.username_edit.setMinimumHeight(36)
        form.addRow("Username:", self.username_edit)
        
        # Password
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setPlaceholderText("Enter password")
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        # larger control for accessibility / spacing
        self.password_edit.setMinimumHeight(36)
        self.password_edit.returnPressed.connect(self.attempt_login)
        form.addRow("Password:", self.password_edit)
        
        layout.addLayout(form)
        
        # Error label
        self.error_label = QtWidgets.QLabel()
        self.error_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
        self.error_label.setAlignment(QtCore.Qt.AlignCenter)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        layout.addStretch()
        
        # Button box
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        
        login_btn = QtWidgets.QPushButton("Login")
        login_btn.setFixedHeight(32)
        login_btn.setMinimumWidth(100)
        login_btn.setObjectName('primary')
        login_btn.setProperty('class', 'primary')
        login_btn.clicked.connect(self.attempt_login)
        button_layout.addWidget(login_btn)
        
        guest_btn = QtWidgets.QPushButton("Continue as Guest")
        guest_btn.setFixedHeight(32)
        guest_btn.setMinimumWidth(140)
        guest_btn.setObjectName('small')
        guest_btn.setProperty('class', 'small')
        guest_btn.clicked.connect(self.continue_as_guest)
        button_layout.addWidget(guest_btn)
        
        layout.addLayout(button_layout)
        
        # Info label
        info_label = QtWidgets.QLabel("Default: admin / admin")
        info_label.setStyleSheet("color: #666666; font-size: 10px; font-style: italic;")
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # Focus username
        self.username_edit.setFocus()
    
    def attempt_login(self):
        """Attempt to authenticate user."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        
        if not username or not password:
            self.show_error("Please enter both username and password")
            return
        
        # Authenticate
        user = self.db.authenticate_user(username, password)
        
        if user:
            self.authenticated_user = user
            
            # Create session
            import socket
            machine_name = socket.gethostname()
            self.db.create_session(user['user_id'], machine_name)
            
            self.accept()
        else:
            self.show_error("Invalid username or password")
            self.password_edit.clear()
            self.password_edit.setFocus()
    
    def continue_as_guest(self):
        """Continue without authentication (read-only mode)."""
        # Create a guest user object
        self.authenticated_user = {
            'user_id': None,
            'username': 'guest',
            'role': 'user',
            'email': None
        }
        self.accept()
    
    def show_error(self, message):
        """Show error message."""
        self.error_label.setText(message)
        self.error_label.show()




class EditElementDialog(QtWidgets.QDialog):
    """Dialog for editing element metadata."""
    
    def __init__(self, db_manager, element_id, parent=None):
        super(EditElementDialog, self).__init__(parent)
        self.db = db_manager
        self.element_id = element_id
        self.element_data = self.db.get_element_by_id(element_id)
        
        if not self.element_data:
            raise ValueError("Element not found")
        
        self.setWindowTitle("Edit Element: {}".format(self.element_data['name']))
        self.setModal(True)
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Form layout for fields
        form = QtWidgets.QFormLayout()
        
        # Name (read-only for display)
        self.name_label = QtWidgets.QLabel(self.element_data['name'])
        self.name_label.setStyleSheet("font-weight: bold; color: #ffffff;")
        form.addRow("Name:", self.name_label)
        
        # Type (read-only)
        self.type_label = QtWidgets.QLabel(self.element_data['type'])
        form.addRow("Type:", self.type_label)
        
        # Format (read-only)
        format_str = self.element_data.get('format', 'N/A') or 'N/A'
        self.format_label = QtWidgets.QLabel(format_str)
        form.addRow("Format:", self.format_label)
        
        # Frame Range (editable for sequences)
        self.frame_range_edit = QtWidgets.QLineEdit()
        self.frame_range_edit.setPlaceholderText("e.g., 1001-1100")
        form.addRow("Frame Range:", self.frame_range_edit)
        
        # Comment (editable)
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlaceholderText("Add descriptive comment...")
        self.comment_edit.setMaximumHeight(80)
        form.addRow("Comment:", self.comment_edit)
        
        # Tags (editable with autocomplete)
        tags_container = QtWidgets.QWidget()
        tags_layout = QtWidgets.QVBoxLayout(tags_container)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tags_edit = QtWidgets.QLineEdit()
        self.tags_edit.setPlaceholderText("Comma-separated tags (e.g., fire, explosion, outdoor)")
        
        # Setup autocomplete for tags
        all_tags = self.db.get_all_tags()
        completer = QtWidgets.QCompleter(all_tags)
        completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self.tags_edit.setCompleter(completer)
        
        tags_layout.addWidget(self.tags_edit)
        
        # Tag suggestions label
        self.tag_suggestions_label = QtWidgets.QLabel()
        self.tag_suggestions_label.setStyleSheet("color: #16c6b0; font-size: 10px; font-style: italic;")
        self.tag_suggestions_label.setWordWrap(True)
        if all_tags:
            popular_tags = all_tags[:10]  # Show first 10
            self.tag_suggestions_label.setText("Popular tags: " + ", ".join(popular_tags))
        tags_layout.addWidget(self.tag_suggestions_label)
        
        form.addRow("Tags:", tags_container)
        
        # Deprecated checkbox
        self.deprecated_checkbox = QtWidgets.QCheckBox("Mark as Deprecated")
        self.deprecated_checkbox.setStyleSheet("color: #ff9a3c;")
        form.addRow("", self.deprecated_checkbox)
        
        layout.addLayout(form)
        
        # Info label
        info_label = QtWidgets.QLabel("Note: Name, type, and format cannot be changed after ingestion.")
        info_label.setStyleSheet("color: #888888; font-style: italic; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.save_changes)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_data(self):
        """Load element data into form fields."""
        self.frame_range_edit.setText(self.element_data.get('frame_range', '') or '')
        self.comment_edit.setPlainText(self.element_data.get('comment', '') or '')
        self.tags_edit.setText(self.element_data.get('tags', '') or '')
        self.deprecated_checkbox.setChecked(self.element_data.get('is_deprecated', 0) == 1)
    
    def save_changes(self):
        """Save changes to database."""
        try:
            # Gather updated data
            updates = {
                'frame_range': self.frame_range_edit.text().strip() or None,
                'comment': self.comment_edit.toPlainText().strip() or None,
                'tags': self.tags_edit.text().strip() or None,
                'is_deprecated': 1 if self.deprecated_checkbox.isChecked() else 0
            }
            
            # Update database
            self.db.update_element(self.element_id, **updates)
            
            QtWidgets.QMessageBox.information(self, "Success", "Element updated successfully!")
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to update element: {}".format(str(e)))




class RegisterToolsetDialog(QtWidgets.QDialog):
    """Dialog for registering selected Nuke nodes as a toolset."""
    
    def __init__(self, db_manager, nuke_integration, config, parent=None):
        super(RegisterToolsetDialog, self).__init__(parent)
        self.db = db_manager
        self.nuke_integration = nuke_integration
        self.config = config
        
        self.setWindowTitle("Register Toolset")
        self.setMinimumWidth(500)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Info label
        info_label = QtWidgets.QLabel(
            "Save the currently selected nodes in Nuke as a reusable toolset.\n"
            "The toolset will be saved as a .nk file and cataloged for easy access."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px; background: #2a2a2a; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        
        # Toolset name
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g., 'Glow and Sharpen'")
        form.addRow("Toolset Name:", self.name_edit)
        
        # List selection
        self.list_combo = QtWidgets.QComboBox()
        self.load_lists()
        form.addRow("Save to List:", self.list_combo)
        
        # Comment
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlaceholderText("Optional description of the toolset...")
        self.comment_edit.setMaximumHeight(80)
        form.addRow("Comment:", self.comment_edit)
        
        layout.addLayout(form)
        
        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept_toolset)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_lists(self):
        """Load available lists into combo box."""
        # Get all lists from all stacks
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                self.list_combo.addItem(
                    "{} > {}".format(stack['name'], lst['name']),
                    lst['list_id']
                )
    
    def accept_toolset(self):
        """Save toolset and ingest into database."""
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing Name", "Please enter a toolset name.")
            return
        
        list_id = self.list_combo.currentData()
        if not list_id:
            QtWidgets.QMessageBox.warning(self, "No List", "Please select a list to save the toolset to.")
            return
        
        try:
            comment_text = self.comment_edit.toPlainText().strip() or None

            element_id = self.nuke_integration.register_selection_as_toolset(
                name,
                list_id,
                comment=comment_text,
                preview_path=None
            )

            QtWidgets.QMessageBox.information(
                self,
                "Toolset Registered",
                "Toolset '{}' has been saved and cataloged successfully!".format(name)
            )
            
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                "Failed to register toolset: {}".format(str(e))
            )



class NukeInstallerDialog(QtWidgets.QDialog):
    """Dialog to install StaX into a Nuke user directory by appending a pluginAddPath line to `init.py`."""

    def __init__(self, parent=None):
        super(NukeInstallerDialog, self).__init__(parent)
        self.setWindowTitle("Install StaX into Nuke")
        self.setMinimumWidth(560)
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        info = QtWidgets.QLabel(
            "Select your Nuke user directory (the folder that contains `init.py`) and click Install.\n"
            "StaX will append a `nuke.pluginAddPath(...)` line to that `init.py` so Nuke can find the plugin."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QtWidgets.QHBoxLayout()
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText(r"C:\Users\<username>\.nuke")
        form.addWidget(self.path_edit)

        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.setObjectName('small')
        browse_btn.clicked.connect(self.browse)
        form.addWidget(browse_btn)

        layout.addLayout(form)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(self.status_label)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        self.install_btn = QtWidgets.QPushButton("Install")
        self.install_btn.setObjectName('primary')
        self.install_btn.clicked.connect(self.install)
        btn_layout.addWidget(self.install_btn)

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setObjectName('small')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def browse(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Nuke user directory")
        if path:
            self.path_edit.setText(path)

    def install(self):
        import os
        import codecs

        dir_path = self.path_edit.text().strip()
        if not dir_path:
            QtWidgets.QMessageBox.warning(self, "No Directory", "Please select a Nuke user directory.")
            return

        init_path = os.path.join(dir_path, 'init.py')
        if not os.path.exists(init_path):
            QtWidgets.QMessageBox.warning(self, "init.py Not Found", "No `init.py` file was found in the selected directory.")
            return

        # Determine application root (two levels up from src/ui)
        app_root = os.path.normpath(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

        add_line = "nuke.pluginAddPath(r'{}')\n".format(app_root)

        try:
            # Read existing content
            with codecs.open(init_path, 'r', encoding='utf-8') as fh:
                content = fh.read()

            # Check for existing similar entry
            if "nuke.pluginAddPath" in content and app_root in content:
                QtWidgets.QMessageBox.information(self, "Already Installed", "StaX is already added to this init.py.")
                return

            # Append the line
            if not content.endswith('\n'):
                content += '\n'
            content += "# StaX plugin path added by installer\n" + add_line

            # Write back
            with codecs.open(init_path, 'w', encoding='utf-8') as fh:
                fh.write(content)

            QtWidgets.QMessageBox.information(self, "Installed", "StaX plugin path appended to init.py successfully.")
            self.accept()

        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to update init.py: {}".format(exc))


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
    
    # Load and apply stylesheet
    stylesheet_path = os.path.join(os.path.dirname(__file__), 'resources', 'style.qss')
    if os.path.exists(stylesheet_path):
        try:
            with open(stylesheet_path, 'r') as f:
                stylesheet = f.read()
                app.setStyleSheet(stylesheet)
                print("Applied stylesheet from: {}".format(stylesheet_path))
        except Exception as e:
            print("Failed to load stylesheet: {}".format(e))
    else:
        print("Stylesheet not found at: {}".format(stylesheet_path))
    
    import importlib
    MainWindow = None
    try:
        module = importlib.import_module('main')
        MainWindow = getattr(module, 'MainWindow', None)
    except Exception as import_error:
        print("MainWindow unavailable: {}".format(import_error))
        MainWindow = None

    if MainWindow is None:
        print("MainWindow class could not be loaded; aborting standalone dialog test.")
        return

    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


class AddUserDialog(QtWidgets.QDialog):
    """Dialog for adding a new user."""
    
    def __init__(self, db_manager, parent=None):
        super(AddUserDialog, self).__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Add New User")
        self.setModal(True)
        self.setFixedSize(400, 350)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Title
        title = QtWidgets.QLabel("Create New User Account")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #16c6b0;")
        layout.addWidget(title)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        
        # Username
        self.username_edit = QtWidgets.QLineEdit()
        self.username_edit.setPlaceholderText("Enter username")
        form.addRow("Username:", self.username_edit)
        
        # Password
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setPlaceholderText("Enter password")
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Password:", self.password_edit)
        
        # Confirm Password
        self.confirm_password_edit = QtWidgets.QLineEdit()
        self.confirm_password_edit.setPlaceholderText("Confirm password")
        self.confirm_password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Confirm Password:", self.confirm_password_edit)
        
        # Email
        self.email_edit = QtWidgets.QLineEdit()
        self.email_edit.setPlaceholderText("user@example.com (optional)")
        form.addRow("Email:", self.email_edit)
        
        # Role
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItems(['user', 'admin'])
        form.addRow("Role:", self.role_combo)
        
        layout.addLayout(form)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        create_btn = QtWidgets.QPushButton("Create User")
        create_btn.setObjectName('primary')
        create_btn.setProperty('class', 'primary')
        create_btn.clicked.connect(self.accept)
        button_layout.addWidget(create_btn)
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setObjectName('small')
        cancel_btn.setProperty('class', 'small')
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def accept(self):
        """Validate and create user."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        confirm = self.confirm_password_edit.text()
        email = self.email_edit.text().strip() or None
        role = self.role_combo.currentText()
        
        # Validation
        if not username:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Username is required.")
            return
        
        if not password:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Password is required.")
            return
        
        if password != confirm:
            QtWidgets.QMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
            return
        
        if len(password) < 4:
            QtWidgets.QMessageBox.warning(self, "Weak Password", "Password must be at least 4 characters.")
            return
        
        # Check if username exists
        if self.db.authenticate_user(username, "dummy"):  # Simple existence check
            QtWidgets.QMessageBox.warning(self, "User Exists", "Username '{}' already exists.".format(username))
            return
        
        # Create user
        try:
            user_id = self.db.create_user(username, password, role, email)
            if user_id:
                QtWidgets.QMessageBox.information(self, "Success", "User '{}' created successfully.".format(username))
                super(AddUserDialog, self).accept()
            else:
                QtWidgets.QMessageBox.warning(self, "Error", "Failed to create user.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Error creating user: {}".format(str(e)))


class EditUserDialog(QtWidgets.QDialog):
    """Dialog for editing an existing user."""
    
    def __init__(self, db_manager, user_id, parent=None):
        super(EditUserDialog, self).__init__(parent)
        self.db = db_manager
        self.user_id = user_id
        self.setWindowTitle("Edit User")
        self.setModal(True)
        self.setFixedSize(400, 350)
        self.load_user_data()
        self.setup_ui()
    
    def load_user_data(self):
        """Load existing user data."""
        users = self.db.get_all_users()
        self.user = None
        for u in users:
            if u['user_id'] == self.user_id:
                self.user = u
                break
        
        if not self.user:
            QtWidgets.QMessageBox.warning(self, "Error", "User not found.")
            self.reject()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Title
        title = QtWidgets.QLabel("Edit User: {}".format(self.user['username']))
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #16c6b0;")
        layout.addWidget(title)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        
        # Username (read-only)
        self.username_edit = QtWidgets.QLineEdit(self.user['username'])
        self.username_edit.setReadOnly(True)
        self.username_edit.setStyleSheet("background: #2a2a2a;")
        form.addRow("Username:", self.username_edit)
        
        # New Password (optional)
        self.password_edit = QtWidgets.QLineEdit()
        self.password_edit.setPlaceholderText("Leave blank to keep current")
        self.password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("New Password:", self.password_edit)
        
        # Confirm Password
        self.confirm_password_edit = QtWidgets.QLineEdit()
        self.confirm_password_edit.setPlaceholderText("Confirm new password")
        self.confirm_password_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("Confirm Password:", self.confirm_password_edit)
        
        # Email
        self.email_edit = QtWidgets.QLineEdit(self.user.get('email', '') or '')
        self.email_edit.setPlaceholderText("user@example.com (optional)")
        form.addRow("Email:", self.email_edit)
        
        # Role
        self.role_combo = QtWidgets.QComboBox()
        self.role_combo.addItems(['user', 'admin'])
        self.role_combo.setCurrentText(self.user['role'])
        form.addRow("Role:", self.role_combo)
        
        # Active status
        self.active_checkbox = QtWidgets.QCheckBox("Account Active")
        self.active_checkbox.setChecked(self.user['is_active'])
        form.addRow("Status:", self.active_checkbox)
        
        layout.addLayout(form)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        save_btn = QtWidgets.QPushButton("Save Changes")
        save_btn.setObjectName('primary')
        save_btn.setProperty('class', 'primary')
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setObjectName('small')
        cancel_btn.setProperty('class', 'small')
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def accept(self):
        """Validate and update user."""
        password = self.password_edit.text()
        confirm = self.confirm_password_edit.text()
        email = self.email_edit.text().strip() or None
        role = self.role_combo.currentText()
        is_active = self.active_checkbox.isChecked()
        
        # Validation
        if password:  # Only validate if changing password
            if password != confirm:
                QtWidgets.QMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
                return
            if len(password) < 4:
                QtWidgets.QMessageBox.warning(self, "Weak Password", "Password must be at least 4 characters.")
                return
        
        # Update user
        try:
            if password:
                # Update with new password
                self.db.update_user(self.user_id, password=password, email=email, role=role, is_active=is_active)
            else:
                # Update without changing password
                self.db.update_user(self.user_id, email=email, role=role, is_active=is_active)
            
            QtWidgets.QMessageBox.information(self, "Success", "User updated successfully.")
            super(EditUserDialog, self).accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", "Error updating user: {}".format(str(e)))


class IngestProgressDialog(QtWidgets.QDialog):
    """Progress dialog for file ingestion."""
    def __init__(self, parent=None):
        super(IngestProgressDialog, self).__init__(parent)
        self.setWindowTitle("Ingesting Files")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._cancelled = False
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Status label
        self.status_label = QtWidgets.QLabel("Preparing ingestion...")
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # File label
        self.file_label = QtWidgets.QLabel("")
        self.file_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.file_label)
        
        # Cancel button
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)
    
    def update_progress(self, current, total, filename=""):
        """Update progress bar and labels."""
        if total > 0:
            percent = int((float(current) / float(total)) * 100)
            self.progress_bar.setValue(percent)
        
        self.status_label.setText("Ingesting {} of {}...".format(current, total))
        self.file_label.setText(filename)
        
        # Process events to keep UI responsive
        QtWidgets.QApplication.processEvents()
    
    def cancel(self):
        """Cancel ingestion."""
        self._cancelled = True
        self.reject()
    
    def is_cancelled(self):
        """Check if ingestion was cancelled."""
        return self._cancelled


if __name__ == '__main__':
    main()


