# -*- coding: utf-8 -*-
"""
Dialog Widgets
Collection of dialog classes for StaX application
"""

import os
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
        self.setFixedSize(400, 250)
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
    
    def __init__(self, db_manager, nuke_bridge, config, parent=None):
        super(RegisterToolsetDialog, self).__init__(parent)
        self.db = db_manager
        self.nuke_bridge = nuke_bridge
        self.config = config
        self.toolset_path = None
        
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
        
        # Generate preview option
        self.gen_preview_check = QtWidgets.QCheckBox("Generate preview image")
        self.gen_preview_check.setChecked(True)
        self.gen_preview_check.setToolTip("Capture a preview of the node graph")
        form.addRow("", self.gen_preview_check)
        
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
            # Create toolset file path
            import tempfile
            import hashlib
            import time
            
            # Generate unique filename
            timestamp = str(int(time.time()))
            name_hash = hashlib.md5(name.encode('utf-8')).hexdigest()[:8]
            filename = "toolset_{}_{}.nk".format(name_hash, timestamp)
            
            # Save to temporary location first
            temp_path = os.path.join(tempfile.gettempdir(), filename)
            
            # Save selected nodes as toolset
            success = self.nuke_bridge.save_selected_as_toolset(temp_path)
            
            if not success or not os.path.exists(temp_path):
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to save toolset from Nuke.")
                return
            
            # Determine final storage path
            repository_path = self.config.get('default_repository_path')
            if not os.path.exists(repository_path):
                os.makedirs(repository_path)
            
            final_path = os.path.join(repository_path, filename)
            
            # Move toolset file to repository
            import shutil
            shutil.move(temp_path, final_path)
            
            # Generate preview if requested
            preview_path = None
            if self.gen_preview_check.isChecked():
                preview_dir = self.config.get('preview_dir')
                if not os.path.exists(preview_dir):
                    os.makedirs(preview_dir)
                
                preview_filename = "toolset_{}_{}.png".format(name_hash, timestamp)
                preview_path = os.path.join(preview_dir, preview_filename)
                
                # Capture node graph preview (if available)
                try:
                    self.nuke_bridge.capture_node_graph_preview(preview_path)
                except Exception as e:
                    print("Preview generation failed: {}".format(str(e)))
                    preview_path = None
            
            # Ingest toolset into database
            element_data = {
                'name': name,
                'list_fk': list_id,
                'type': 'toolset',
                'format': 'nk',
                'filepath_soft': None,  # Toolset is always hard copy
                'filepath_hard': final_path,
                'is_hard_copy': True,
                'preview_path': preview_path,
                'comment': self.comment_edit.toPlainText().strip() or None,
                'frames': 1,
                'width': None,
                'height': None,
                'size_bytes': os.path.getsize(final_path)
            }
            
            element_id = self.db.add_element(**element_data)
            
            # Log to history
            self.db.add_history_entry(
                'toolset_registered',
                "Registered toolset: {}".format(name),
                {'element_id': element_id, 'list_id': list_id}
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
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()


