# -*- coding: utf-8 -*-
"""
Settings Panel Widget
"""

import os
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon, get_pixmap
from src.preview_cache import get_preview_cache


class SettingsPanel(QtWidgets.QWidget):
    """Comprehensive panel for application settings with tabbed interface."""
    
    settings_changed = QtCore.Signal()
    
    def __init__(self, config, db_manager, main_window=None, parent=None):
        super(SettingsPanel, self).__init__(parent)
        self.config = config
        self.db = db_manager
        self.main_window = main_window  # For permission checks
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components with tabs."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Title
        title = QtWidgets.QLabel("Application Settings")
        title.setStyleSheet("font-weight: bold; font-size: 16px; color: #16c6b0; padding: 10px;")
        layout.addWidget(title)
        
        # Tab widget for organized settings
        self.tab_widget = QtWidgets.QTabWidget()
        self.tab_widget.setStyleSheet("QTabWidget::pane { border: 1px solid #333; }")
        
        # Tab 1: General Settings
        self.setup_general_tab()
        
        # Tab 2: Ingestion Settings
        self.setup_ingestion_tab()
        
        # Tab 3: Preview & Media Settings
        self.setup_preview_tab()
        
        # Tab 4: Network & Performance
        self.setup_network_tab()
        
        # Tab 5: Custom Processors
        self.setup_processors_tab()
        
        # Tab 6: Security & Admin (Admin only)
        self.setup_security_tab()
        
        layout.addWidget(self.tab_widget)
        
        # Bottom buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        save_btn = QtWidgets.QPushButton("Save All Settings")
        save_btn.setIcon(get_icon('settings', size=20))
        save_btn.setObjectName('primary')
        save_btn.setProperty('class', 'primary')
        save_btn.clicked.connect(self.save_all_settings)
        button_layout.addWidget(save_btn)
        
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        reset_btn.setIcon(get_icon('refresh', size=20))
        reset_btn.setObjectName('small')
        reset_btn.setProperty('class', 'small')
        reset_btn.clicked.connect(self.reset_settings)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        # Current user indicator
        if self.main_window and self.main_window.current_user:
            user_label = QtWidgets.QLabel("Logged in as: {}".format(
                self.main_window.current_user['username']
            ))
            user_label.setStyleSheet("color: #888; font-size: 11px;")
            button_layout.addWidget(user_label)
        
        layout.addLayout(button_layout)
    
    def setup_general_tab(self):
        """Setup general settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # Database location
        db_group = QtWidgets.QGroupBox("Database Configuration")
        db_layout = QtWidgets.QFormLayout()
        
        self.db_path_edit = QtWidgets.QLineEdit(self.config.get('database_path'))
        self.db_path_edit.setReadOnly(True)
        db_path_layout = QtWidgets.QHBoxLayout()
        db_path_layout.addWidget(self.db_path_edit)
        
        browse_db_btn = QtWidgets.QPushButton("Browse...")
        browse_db_btn.setObjectName('small')
        browse_db_btn.setProperty('class', 'small')
        browse_db_btn.clicked.connect(self.browse_database_path)
        db_path_layout.addWidget(browse_db_btn)
        
        db_layout.addRow("Database Path:", db_path_layout)
        
        # Environment variable hint
        env_hint = QtWidgets.QLabel("Tip: Set STOCK_DB environment variable to override")
        env_hint.setStyleSheet("color: #16c6b0; font-size: 10px; font-style: italic;")
        db_layout.addRow("", env_hint)
        
        db_group.setLayout(db_layout)
        layout.addWidget(db_group)
        
        # User preferences
        pref_group = QtWidgets.QGroupBox("User Preferences")
        pref_layout = QtWidgets.QFormLayout()
        
        self.user_name_edit = QtWidgets.QLineEdit(self.config.get('user_name') or '')
        pref_layout.addRow("User Name:", self.user_name_edit)
        
        import socket
        self.machine_name_edit = QtWidgets.QLineEdit(self.config.get('machine_name') or socket.gethostname())
        self.machine_name_edit.setReadOnly(True)
        pref_layout.addRow("Machine Name:", self.machine_name_edit)
        
        pref_group.setLayout(pref_layout)
        layout.addWidget(pref_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "General")
    
    def setup_ingestion_tab(self):
        """Setup ingestion settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Copy policy
        policy_group = QtWidgets.QGroupBox("File Copy Policy")
        policy_layout = QtWidgets.QFormLayout()
        
        self.copy_policy = QtWidgets.QComboBox()
        self.copy_policy.addItems(['soft', 'hard'])
        self.copy_policy.setCurrentText(self.config.get('default_copy_policy'))
        policy_layout.addRow("Default Copy Policy:", self.copy_policy)
        
        policy_help = QtWidgets.QLabel(
            "- Soft: Store reference to original file location\n"
            "- Hard: Copy file to repository"
        )
        policy_help.setStyleSheet("color: #888; font-size: 11px;")
        policy_layout.addRow("", policy_help)
        
        policy_group.setLayout(policy_layout)
        layout.addWidget(policy_group)
        
        # Sequence detection
        seq_group = QtWidgets.QGroupBox("Sequence Detection")
        seq_layout = QtWidgets.QFormLayout()
        
        self.auto_detect = QtWidgets.QCheckBox("Auto-detect image sequences")
        self.auto_detect.setChecked(self.config.get('auto_detect_sequences'))
        seq_layout.addRow("", self.auto_detect)
        
        seq_group.setLayout(seq_layout)
        layout.addWidget(seq_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Ingestion")
    
    def setup_preview_tab(self):
        """Setup preview and media settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Preview generation
        prev_group = QtWidgets.QGroupBox("Preview Generation")
        prev_layout = QtWidgets.QFormLayout()
        
        self.gen_previews = QtWidgets.QCheckBox("Generate preview thumbnails")
        self.gen_previews.setChecked(self.config.get('generate_previews'))
        prev_layout.addRow("", self.gen_previews)
        
        self.preview_size = QtWidgets.QSpinBox()
        self.preview_size.setRange(128, 2048)
        self.preview_size.setValue(self.config.get('preview_size', 512))
        self.preview_size.setSuffix(" px")
        prev_layout.addRow("Preview Size:", self.preview_size)
        
        self.preview_quality = QtWidgets.QSpinBox()
        self.preview_quality.setRange(1, 100)
        self.preview_quality.setValue(self.config.get('preview_quality', 85))
        self.preview_quality.setSuffix(" %")
        prev_layout.addRow("JPEG Quality:", self.preview_quality)
        
        prev_group.setLayout(prev_layout)
        layout.addWidget(prev_group)
        
        # GIF settings
        gif_group = QtWidgets.QGroupBox("Animated GIF Settings")
        gif_layout = QtWidgets.QFormLayout()
        
        self.gif_size = QtWidgets.QSpinBox()
        self.gif_size.setRange(128, 512)
        self.gif_size.setValue(self.config.get('gif_size', 256))
        self.gif_size.setSuffix(" px")
        gif_layout.addRow("GIF Size:", self.gif_size)
        
        self.gif_fps = QtWidgets.QSpinBox()
        self.gif_fps.setRange(5, 30)
        self.gif_fps.setValue(self.config.get('gif_fps', 10))
        self.gif_fps.setSuffix(" fps")
        gif_layout.addRow("GIF Frame Rate:", self.gif_fps)
        
        self.gif_duration = QtWidgets.QDoubleSpinBox()
        self.gif_duration.setRange(1.0, 10.0)
        self.gif_duration.setValue(self.config.get('gif_duration', 3.0))
        self.gif_duration.setSuffix(" sec")
        gif_layout.addRow("GIF Duration:", self.gif_duration)
        
        gif_group.setLayout(gif_layout)
        layout.addWidget(gif_group)
        
        # FFmpeg settings
        ffmpeg_group = QtWidgets.QGroupBox("FFmpeg Settings")
        ffmpeg_layout = QtWidgets.QFormLayout()
        
        self.ffmpeg_threads = QtWidgets.QSpinBox()
        self.ffmpeg_threads.setRange(1, 16)
        self.ffmpeg_threads.setValue(self.config.get('ffmpeg_threads', 4))
        self.ffmpeg_threads.setSuffix(" threads")
        ffmpeg_layout.addRow("Thread Count:", self.ffmpeg_threads)
        
        thread_help = QtWidgets.QLabel("Higher values = faster processing, more CPU usage")
        thread_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        ffmpeg_layout.addRow("", thread_help)
        
        ffmpeg_group.setLayout(ffmpeg_layout)
        layout.addWidget(ffmpeg_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Preview & Media")
    
    def setup_network_tab(self):
        """Setup network and performance settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Network settings
        net_group = QtWidgets.QGroupBox("Network Database Settings")
        net_layout = QtWidgets.QFormLayout()
        
        self.db_retries = QtWidgets.QSpinBox()
        self.db_retries.setRange(1, 50)
        self.db_retries.setValue(self.config.get('db_max_retries', 10))
        net_layout.addRow("Max Connection Retries:", self.db_retries)
        
        self.db_timeout = QtWidgets.QSpinBox()
        self.db_timeout.setRange(5, 300)
        self.db_timeout.setValue(self.config.get('db_timeout', 60))
        self.db_timeout.setSuffix(" sec")
        net_layout.addRow("Connection Timeout:", self.db_timeout)
        
        net_help = QtWidgets.QLabel(
            "These settings help handle network database access.\n"
            "Increase values for slow/unreliable network connections."
        )
        net_help.setStyleSheet("color: #888; font-size: 11px;")
        net_layout.addRow("", net_help)
        
        net_group.setLayout(net_layout)
        layout.addWidget(net_group)
        
        # Performance settings
        perf_group = QtWidgets.QGroupBox("Performance & Caching")
        perf_layout = QtWidgets.QFormLayout()
        
        self.cache_size = QtWidgets.QSpinBox()
        self.cache_size.setRange(50, 1000)
        self.cache_size.setValue(self.config.get('preview_cache_size', 200))
        self.cache_size.setSuffix(" items")
        perf_layout.addRow("Preview Cache Size:", self.cache_size)
        
        self.cache_memory = QtWidgets.QSpinBox()
        self.cache_memory.setRange(50, 1000)
        self.cache_memory.setValue(self.config.get('preview_cache_memory_mb', 200))
        self.cache_memory.setSuffix(" MB")
        perf_layout.addRow("Cache Memory Limit:", self.cache_memory)
        
        # Pagination settings
        self.pagination_enabled = QtWidgets.QCheckBox()
        self.pagination_enabled.setChecked(self.config.get('pagination_enabled', True))
        perf_layout.addRow("Enable Pagination:", self.pagination_enabled)
        
        self.items_per_page = QtWidgets.QComboBox()
        self.items_per_page.addItems(['50', '100', '200', '500'])
        self.items_per_page.setCurrentText(str(self.config.get('items_per_page', 100)))
        perf_layout.addRow("Items Per Page:", self.items_per_page)
        
        self.background_loading = QtWidgets.QCheckBox()
        self.background_loading.setChecked(self.config.get('background_thumbnail_loading', True))
        perf_layout.addRow("Background Thumbnail Loading:", self.background_loading)
        
        perf_help = QtWidgets.QLabel(
            "Pagination reduces memory usage and improves performance\n"
            "for large element collections. Background loading prevents UI freezing."
        )
        perf_help.setStyleSheet("color: #888; font-size: 11px;")
        perf_layout.addRow("", perf_help)
        
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Network & Performance")
    
    def setup_processors_tab(self):
        """Setup custom processors tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        help_label = QtWidgets.QLabel(
            "Custom processors allow you to run Python scripts at key points in the workflow.\n"
            "Leave blank to disable."
        )
        help_label.setStyleSheet("color: #16c6b0; font-size: 11px; padding: 10px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        
        # Processor hooks
        proc_group = QtWidgets.QGroupBox("Processor Hooks")
        proc_layout = QtWidgets.QFormLayout()
        
        # Pre-ingest
        self.pre_ingest = QtWidgets.QLineEdit(self.config.get('pre_ingest_processor') or '')
        pre_layout = QtWidgets.QHBoxLayout()
        pre_layout.addWidget(self.pre_ingest)
        pre_browse = QtWidgets.QPushButton("Browse...")
        pre_browse.setObjectName('small')
        pre_browse.setProperty('class', 'small')
        pre_browse.clicked.connect(lambda: self.browse_file(self.pre_ingest))
        pre_layout.addWidget(pre_browse)
        proc_layout.addRow("Pre-Ingest Hook:", pre_layout)
        
        pre_help = QtWidgets.QLabel("Runs before file copy/metadata extraction")
        pre_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        proc_layout.addRow("", pre_help)
        
        # Post-ingest
        self.post_ingest = QtWidgets.QLineEdit(self.config.get('post_ingest_processor') or '')
        post_layout = QtWidgets.QHBoxLayout()
        post_layout.addWidget(self.post_ingest)
        post_browse = QtWidgets.QPushButton("Browse...")
        post_browse.setObjectName('small')
        post_browse.setProperty('class', 'small')
        post_browse.clicked.connect(lambda: self.browse_file(self.post_ingest))
        post_layout.addWidget(post_browse)
        proc_layout.addRow("Post-Ingest Hook:", post_layout)
        
        post_help = QtWidgets.QLabel("Runs after asset is cataloged in database")
        post_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        proc_layout.addRow("", post_help)
        
        # Post-import
        self.post_import = QtWidgets.QLineEdit(self.config.get('post_import_processor') or '')
        import_layout = QtWidgets.QHBoxLayout()
        import_layout.addWidget(self.post_import)
        import_browse = QtWidgets.QPushButton("Browse...")
        import_browse.setObjectName('small')
        import_browse.setProperty('class', 'small')
        import_browse.clicked.connect(lambda: self.browse_file(self.post_import))
        import_layout.addWidget(import_browse)
        proc_layout.addRow("Post-Import Hook:", import_layout)
        
        import_help = QtWidgets.QLabel("Runs after Nuke node creation")
        import_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        proc_layout.addRow("", import_help)
        
        proc_group.setLayout(proc_layout)
        layout.addWidget(proc_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Custom Processors")
    
    def setup_security_tab(self):
        """Setup security and admin settings tab (Admin only)."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Check if admin
        is_admin = False
        if self.main_window and self.main_window.is_admin:
            is_admin = True
        
        if not is_admin:
            # Show locked message for non-admin users
            lock_label = QtWidgets.QLabel(
                "Administrator Privileges Required\n\n"
                "This section contains sensitive settings that can only\n"
                "be modified by users with administrator privileges.\n\n"
                "Current user: {}\n"
                "Role: {}".format(
                    self.main_window.current_user['username'] if self.main_window and self.main_window.current_user else 'guest',
                    self.main_window.current_user.get('role', 'guest') if self.main_window and self.main_window.current_user else 'guest'
                )
            )
            lock_label.setAlignment(QtCore.Qt.AlignCenter)
            lock_label.setStyleSheet("color: #ff9a3c; font-size: 13px; padding: 50px;")
            layout.addWidget(lock_label)
        else:
            # Admin password change
            pwd_group = QtWidgets.QGroupBox("Change Admin Password")
            pwd_layout = QtWidgets.QFormLayout()
            
            self.current_pwd = QtWidgets.QLineEdit()
            self.current_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
            pwd_layout.addRow("Current Password:", self.current_pwd)
            
            self.new_pwd = QtWidgets.QLineEdit()
            self.new_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
            pwd_layout.addRow("New Password:", self.new_pwd)
            
            self.confirm_pwd = QtWidgets.QLineEdit()
            self.confirm_pwd.setEchoMode(QtWidgets.QLineEdit.Password)
            pwd_layout.addRow("Confirm Password:", self.confirm_pwd)
            
            change_pwd_btn = QtWidgets.QPushButton("Change Password")
            change_pwd_btn.setObjectName('primary')
            change_pwd_btn.setProperty('class', 'primary')
            change_pwd_btn.clicked.connect(self.change_admin_password)
            pwd_layout.addRow("", change_pwd_btn)
            
            pwd_group.setLayout(pwd_layout)
            layout.addWidget(pwd_group)
            
            # User management
            user_group = QtWidgets.QGroupBox("User Management")
            user_layout = QtWidgets.QVBoxLayout()
            
            users_label = QtWidgets.QLabel("Registered Users:")
            users_label.setStyleSheet("font-weight: bold;")
            user_layout.addWidget(users_label)
            
            self.users_list = QtWidgets.QTableWidget()
            self.users_list.setColumnCount(4)
            self.users_list.setHorizontalHeaderLabels(['Username', 'Role', 'Email', 'Active'])
            self.users_list.horizontalHeader().setStretchLastSection(True)
            self.load_users_list()
            user_layout.addWidget(self.users_list)
            
            user_btn_layout = QtWidgets.QHBoxLayout()
            
            add_user_btn = QtWidgets.QPushButton("Add User")
            add_user_btn.setObjectName('primary')
            add_user_btn.setProperty('class', 'primary')
            add_user_btn.clicked.connect(self.add_user)
            user_btn_layout.addWidget(add_user_btn)
            
            edit_user_btn = QtWidgets.QPushButton("Edit User")
            edit_user_btn.setObjectName('small')
            edit_user_btn.setProperty('class', 'small')
            edit_user_btn.clicked.connect(self.edit_user)
            user_btn_layout.addWidget(edit_user_btn)
            
            deactivate_user_btn = QtWidgets.QPushButton("Deactivate User")
            deactivate_user_btn.setObjectName('small')
            deactivate_user_btn.setProperty('class', 'small')
            deactivate_user_btn.clicked.connect(self.deactivate_user)
            user_btn_layout.addWidget(deactivate_user_btn)
            
            user_btn_layout.addStretch()
            user_layout.addLayout(user_btn_layout)
            
            user_group.setLayout(user_layout)
            layout.addWidget(user_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Security & Admin")
    
    def browse_database_path(self):
        """Browse for database file."""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select Database File", self.db_path_edit.text(), "SQLite Database (*.db)"
        )
        if filename:
            self.db_path_edit.setText(filename)
    
    def browse_file(self, line_edit):
        """Browse for processor script file."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Processor Script", "", "Python Files (*.py)"
        )
        if filename:
            line_edit.setText(filename)
    
    def load_users_list(self):
        """Load users into table."""
        if not hasattr(self, 'users_list'):
            return
        
        users = self.db.get_all_users()
        self.users_list.setRowCount(len(users))
        
        for row, user in enumerate(users):
            self.users_list.setItem(row, 0, QtWidgets.QTableWidgetItem(user['username']))
            self.users_list.setItem(row, 1, QtWidgets.QTableWidgetItem(user['role']))
            self.users_list.setItem(row, 2, QtWidgets.QTableWidgetItem(user.get('email', '') or ''))
            self.users_list.setItem(row, 3, QtWidgets.QTableWidgetItem('Yes' if user['is_active'] else 'No'))
            
            # Store user_id in first column
            self.users_list.item(row, 0).setData(QtCore.Qt.UserRole, user['user_id'])
    
    def add_user(self):
        """Add new user dialog."""
        # TODO: Implement AddUserDialog
        QtWidgets.QMessageBox.information(self, "Coming Soon", "User management dialog will be implemented.")
    
    def edit_user(self):
        """Edit selected user."""
        # TODO: Implement EditUserDialog
        QtWidgets.QMessageBox.information(self, "Coming Soon", "User editing dialog will be implemented.")
    
    def deactivate_user(self):
        """Deactivate selected user."""
        current_row = self.users_list.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a user to deactivate.")
            return
        
        user_id = self.users_list.item(current_row, 0).data(QtCore.Qt.UserRole)
        username = self.users_list.item(current_row, 0).text()
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deactivation",
            "Are you sure you want to deactivate user '{}'?".format(username),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.db.delete_user(user_id)
            self.load_users_list()
            QtWidgets.QMessageBox.information(self, "Success", "User deactivated successfully.")
    
    def change_admin_password(self):
        """Change admin password."""
        current = self.current_pwd.text()
        new = self.new_pwd.text()
        confirm = self.confirm_pwd.text()
        
        if not current or not new or not confirm:
            QtWidgets.QMessageBox.warning(self, "Invalid Input", "Please fill all password fields.")
            return
        
        if new != confirm:
            QtWidgets.QMessageBox.warning(self, "Password Mismatch", "New password and confirmation do not match.")
            return
        
        if len(new) < 4:
            QtWidgets.QMessageBox.warning(self, "Weak Password", "Password must be at least 4 characters.")
            return
        
        # Verify current password
        if self.main_window and self.main_window.current_user:
            user = self.db.authenticate_user(
                self.main_window.current_user['username'],
                current
            )
            
            if not user:
                QtWidgets.QMessageBox.warning(self, "Invalid Password", "Current password is incorrect.")
                return
            
            # Change password
            self.db.change_user_password(user['user_id'], new)
            
            # Clear fields
            self.current_pwd.clear()
            self.new_pwd.clear()
            self.confirm_pwd.clear()
            
            QtWidgets.QMessageBox.information(self, "Success", "Admin password changed successfully!")
    
    def save_all_settings(self):
        """Save all settings to config."""
        # General settings
        self.config.set('database_path', self.db_path_edit.text())
        self.config.set('user_name', self.user_name_edit.text())
        
        # Ingestion settings
        self.config.set('default_copy_policy', self.copy_policy.currentText())
        self.config.set('auto_detect_sequences', self.auto_detect.isChecked())
        
        # Preview settings
        self.config.set('generate_previews', self.gen_previews.isChecked())
        self.config.set('preview_size', self.preview_size.value())
        self.config.set('preview_quality', self.preview_quality.value())
        self.config.set('gif_size', self.gif_size.value())
        self.config.set('gif_fps', self.gif_fps.value())
        self.config.set('gif_duration', self.gif_duration.value())
        self.config.set('ffmpeg_threads', self.ffmpeg_threads.value())
        
        # Network and performance settings
        self.config.set('db_max_retries', self.db_retries.value())
        self.config.set('db_timeout', self.db_timeout.value())
        self.config.set('preview_cache_size', self.cache_size.value())
        self.config.set('preview_cache_memory_mb', self.cache_memory.value())
        self.config.set('pagination_enabled', self.pagination_enabled.isChecked())
        self.config.set('items_per_page', int(self.items_per_page.currentText()))
        self.config.set('background_thumbnail_loading', self.background_loading.isChecked())
        
        # Processor hooks
        self.config.set('pre_ingest_processor', self.pre_ingest.text() or None)
        self.config.set('post_ingest_processor', self.post_ingest.text() or None)
        self.config.set('post_import_processor', self.post_import.text() or None)
        
        QtWidgets.QMessageBox.information(
            self,
            "Settings Saved",
            "All settings have been saved successfully.\n\n"
            "Some changes may require restarting the application."
        )
        self.settings_changed.emit()
    
    def reset_settings(self):
        """Reset settings to defaults."""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to defaults?\n\n"
            "This will not affect your database or user accounts.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            self.config.reset_to_defaults()
            
            # Recreate UI to reload defaults
            # Clear layout
            while self.layout().count():
                child = self.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            # Rebuild UI
            self.setup_ui()
            
            QtWidgets.QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            self.settings_changed.emit()


