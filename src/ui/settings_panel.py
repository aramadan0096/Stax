# -*- coding: utf-8 -*-
"""
Settings Panel Widget
"""

import os
import sys
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon, get_pixmap
from src.preview_cache import get_preview_cache
from src.debug_manager import DebugManager
from src.ui.accessibility import apply_accessibility


class SettingsPanel(QtWidgets.QWidget):
    """Comprehensive panel for application settings with tabbed interface."""
    
    settings_changed = QtCore.Signal()
    
    def __init__(self, config, db_manager, main_window=None, parent=None, accessibility_target=None):
        super(SettingsPanel, self).__init__(parent)
        self.config = config
        self.db = db_manager
        self.main_window = main_window  # For permission checks
        self._last_admin_status = None  # Track admin status for refresh logic
        # Final review Finding 2: StaX runs in two shells sharing this same
        # panel class -- the standalone app, and a dialog opened on top of
        # an embedded Nuke panel (nuke_launcher.StaXPanel), where the live
        # QApplication is Nuke's own. `accessibility_target` lets the host
        # tell this panel what to restyle: the embedded shell passes its
        # own StaXPanel widget so only the StaX subtree is affected, never
        # the whole DCC. Left None (the standalone default) falls back to
        # QApplication.instance() in _on_accessibility_changed, unchanged
        # from prior behaviour.
        self.accessibility_target = accessibility_target
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

        # Tab 7: Labels (EP1 curation palette)
        self.tab_widget.addTab(self._build_labels_tab(), "Labels")

        # Tab 8: Search (EP2 synonyms + smart collections)
        self.tab_widget.addTab(self._build_search_tab(), "Search")

        # Tab 9: Accessibility (EP3 high contrast / text scale / focus assist)
        self.tab_widget.addTab(self._build_accessibility_tab(), "Accessibility")

        # Tab 10: Metadata Fields (EP4 per-stack custom field admin)
        self.tab_widget.addTab(self._build_fields_tab(), "Metadata Fields")

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
    
    def showEvent(self, event):
        """Refresh security tab when panel is shown if admin status changed."""
        super(SettingsPanel, self).showEvent(event)
        
        # Get current admin status
        current_admin_status = self.main_window and self.main_window.is_admin
        
        # Only refresh if admin status has changed since last time
        if self._last_admin_status != current_admin_status:
            self._last_admin_status = current_admin_status
            self.refresh_security_tab()
    
    def refresh_security_tab(self):
        """Rebuild security tab to reflect current admin privileges."""
        # Find and remove existing security tab
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Security Admin":
                self.tab_widget.removeTab(i)
                break
        
        # Recreate security tab with current permissions
        self.setup_security_tab()
    
    def setup_general_tab(self):
        """Setup general settings tab."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # Check if STOCK_DB environment variable is set
        stock_db_env = os.environ.get('STOCK_DB')
        is_env_controlled = stock_db_env is not None
        
        # Database location
        db_group = QtWidgets.QGroupBox("Database Configuration")
        db_layout = QtWidgets.QFormLayout()
        
        self.db_path_edit = QtWidgets.QLineEdit(self.config.get('database_path'))
        self.db_path_edit.setReadOnly(True)
        db_path_layout = QtWidgets.QHBoxLayout()
        db_path_layout.addWidget(self.db_path_edit)
        
        self.browse_db_btn = QtWidgets.QPushButton("Browse...")
        self.browse_db_btn.setObjectName('small')
        self.browse_db_btn.setProperty('class', 'small')
        self.browse_db_btn.clicked.connect(self.browse_database_path)
        db_path_layout.addWidget(self.browse_db_btn)
        
        db_layout.addRow("Database Path:", db_path_layout)
        
        # Environment variable hint/status
        if is_env_controlled:
            env_status = QtWidgets.QLabel("🔒 Controlled by STOCK_DB environment variable")
            env_status.setStyleSheet("color: #ff9a3c; font-size: 10px; font-weight: bold;")
            self.db_path_edit.setEnabled(False)
            self.browse_db_btn.setEnabled(False)
        else:
            env_status = QtWidgets.QLabel("Tip: Set STOCK_DB environment variable to override")
            env_status.setStyleSheet("color: #16c6b0; font-size: 10px; font-style: italic;")
        db_layout.addRow("", env_status)
        
        db_group.setLayout(db_layout)
        layout.addWidget(db_group)
        
        # Previews location
        previews_group = QtWidgets.QGroupBox("Previews Configuration")
        previews_layout = QtWidgets.QFormLayout()
        
        self.previews_path_edit = QtWidgets.QLineEdit(self.config.get('previews_path', './previews'))
        self.previews_path_edit.setReadOnly(True)
        previews_path_layout = QtWidgets.QHBoxLayout()
        previews_path_layout.addWidget(self.previews_path_edit)
        
        self.browse_previews_btn = QtWidgets.QPushButton("Browse...")
        self.browse_previews_btn.setObjectName('small')
        self.browse_previews_btn.setProperty('class', 'small')
        self.browse_previews_btn.clicked.connect(self.browse_previews_path)
        previews_path_layout.addWidget(self.browse_previews_btn)
        
        previews_layout.addRow("Previews Path:", previews_path_layout)
        
        # Environment variable status for previews
        if is_env_controlled:
            previews_env_status = QtWidgets.QLabel("🔒 Controlled by STOCK_DB environment variable")
            previews_env_status.setStyleSheet("color: #ff9a3c; font-size: 10px; font-weight: bold;")
            self.previews_path_edit.setEnabled(False)
            self.browse_previews_btn.setEnabled(False)
        else:
            previews_env_status = QtWidgets.QLabel("Shared location for preview thumbnails and videos")
            previews_env_status.setStyleSheet("color: #888888; font-size: 10px; font-style: italic;")
        previews_layout.addRow("", previews_env_status)
        
        previews_group.setLayout(previews_layout)
        layout.addWidget(previews_group)
        
        # User preferences
        pref_group = QtWidgets.QGroupBox("User Preferences")
        pref_layout = QtWidgets.QFormLayout()
        
        self.user_name_edit = QtWidgets.QLineEdit(self.config.get('user_name') or '')
        pref_layout.addRow("User Name:", self.user_name_edit)
        
        import socket
        self.machine_name_edit = QtWidgets.QLineEdit(self.config.get('machine_name') or socket.gethostname())
        self.machine_name_edit.setReadOnly(True)
        pref_layout.addRow("Machine Name:", self.machine_name_edit)

        self.debug_mode_checkbox = QtWidgets.QCheckBox("Enable Debug Mode (verbose console output)")
        self.debug_mode_checkbox.setChecked(self.config.get('debug_mode', True))
        pref_layout.addRow("Debug Mode:", self.debug_mode_checkbox)

        debug_hint = QtWidgets.QLabel("When disabled, all print statements across StaX are suppressed.")
        debug_hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        debug_hint.setWordWrap(True)
        pref_layout.addRow("", debug_hint)
        
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
        self.auto_detect.toggled.connect(self.on_auto_detect_sequences_toggled)
        seq_layout.addRow("", self.auto_detect)

        # Sequence pattern selection
        pattern_label = QtWidgets.QLabel("Sequence Pattern:")
        pattern_help = QtWidgets.QLabel(
            "Determines how image sequences are detected. '####' represents any number of digits (e.g. 1, 1001, 000034). Files matching the active pattern are grouped into a single sequence."
        )
        pattern_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")

        self.sequence_pattern_combo = QtWidgets.QComboBox()
        pattern_options = ['.####.ext', '_####.ext', ' ####.ext', '-####.ext']
        self.sequence_pattern_combo.addItems(pattern_options)
        current_pattern = self.config.get('sequence_pattern', '.####.ext')
        if current_pattern not in pattern_options:
            current_pattern = '.####.ext'
        self.sequence_pattern_combo.setCurrentText(current_pattern)
        self.sequence_pattern_combo.setEnabled(self.auto_detect.isChecked())
        self.sequence_pattern_combo.currentTextChanged.connect(self.update_sequence_pattern_hint)

        self.sequence_pattern_hint = QtWidgets.QLabel()
        self.sequence_pattern_hint.setStyleSheet("color: #aaa; font-size: 10px;")
        self.sequence_pattern_hint.setWordWrap(True)
        self.update_sequence_pattern_hint(current_pattern)
        self.sequence_pattern_hint.setEnabled(self.auto_detect.isChecked())

        seq_layout.addRow(pattern_label, self.sequence_pattern_combo)
        seq_layout.addRow("", pattern_help)
        seq_layout.addRow("", self.sequence_pattern_hint)
        
        seq_group.setLayout(seq_layout)
        layout.addWidget(seq_group)

        # Geometry conversion
        geometry_group = QtWidgets.QGroupBox("3D Geometry Conversion")
        geometry_layout = QtWidgets.QFormLayout()

        blender_row = QtWidgets.QHBoxLayout()
        self.blender_path_edit = QtWidgets.QLineEdit(self.config.get('blender_path') or '')
        self.blender_path_edit.setPlaceholderText("Optional: full path to blender executable")
        blender_row.addWidget(self.blender_path_edit)

        self.browse_blender_btn = QtWidgets.QPushButton("Browse...")
        self.browse_blender_btn.setObjectName('small')
        self.browse_blender_btn.setProperty('class', 'small')
        self.browse_blender_btn.clicked.connect(self.browse_blender_path)
        blender_row.addWidget(self.browse_blender_btn)

        self.clear_blender_btn = QtWidgets.QPushButton("Clear")
        self.clear_blender_btn.setObjectName('small')
        self.clear_blender_btn.setProperty('class', 'small')
        self.clear_blender_btn.clicked.connect(self.clear_blender_path)
        blender_row.addWidget(self.clear_blender_btn)

        geometry_layout.addRow("Blender Executable:", blender_row)

        blender_help = QtWidgets.QLabel(
            "StaX uses Blender for FBX/Alembic conversions. Set this to the Blender executable when it is not on PATH."
        )
        blender_help.setWordWrap(True)
        blender_help.setStyleSheet("color: #888; font-size: 10px;")
        geometry_layout.addRow("", blender_help)

        geometry_group.setLayout(geometry_layout)
        layout.addWidget(geometry_group)
        
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
        
        # GIF Duration with Full Duration toggle
        duration_container = QtWidgets.QWidget()
        duration_layout = QtWidgets.QHBoxLayout(duration_container)
        duration_layout.setContentsMargins(0, 0, 0, 0)
        
        self.gif_duration = QtWidgets.QDoubleSpinBox()
        self.gif_duration.setRange(1.0, 10.0)
        self.gif_duration.setValue(self.config.get('gif_duration', 3.0))
        self.gif_duration.setSuffix(" sec")
        duration_layout.addWidget(self.gif_duration)
        
        self.gif_full_duration = QtWidgets.QCheckBox("Full Duration")
        self.gif_full_duration.setChecked(self.config.get('gif_full_duration', False))
        self.gif_full_duration.setToolTip("Generate GIF using the full video duration (ignores duration limit)")
        self.gif_full_duration.toggled.connect(self.on_gif_full_duration_toggled)
        duration_layout.addWidget(self.gif_full_duration)
        duration_layout.addStretch()
        
        gif_layout.addRow("GIF Duration:", duration_container)
        
        # Disable duration spinbox if full duration is enabled
        if self.gif_full_duration.isChecked():
            self.gif_duration.setEnabled(False)
        
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
        
        # Stack behavior settings
        stack_group = QtWidgets.QGroupBox("Stack Behavior")
        stack_layout = QtWidgets.QFormLayout()
        
        self.show_entire_stack = QtWidgets.QCheckBox("Show entire stack elements on stack selection")
        self.show_entire_stack.setChecked(self.config.get('show_entire_stack_elements', False))
        stack_layout.addRow("", self.show_entire_stack)
        
        stack_help = QtWidgets.QLabel("When enabled, selecting a stack shows all elements from all lists in that stack")
        stack_help.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        stack_help.setWordWrap(True)
        stack_layout.addRow("", stack_help)
        
        stack_group.setLayout(stack_layout)
        layout.addWidget(stack_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Preview Media")
    
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
        self.tab_widget.addTab(tab, "Network Performance")
    
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
            # Show a contrasted lock-card for non-admin users
            lock_card = QtWidgets.QWidget()
            lock_card.setObjectName('lockCard')
            lock_card_layout = QtWidgets.QHBoxLayout(lock_card)
            lock_card_layout.setContentsMargins(16, 16, 16, 16)
            lock_card_layout.setSpacing(12)

            # Lock icon (use an existing pause/play icon color via SVG 'currentColor')
            lock_icon_lbl = QtWidgets.QLabel()
            lock_icon_lbl.setFixedSize(48, 48)
            lock_pix = get_pixmap('lock', size=48) if hasattr(__import__('src.icon_loader'), 'get_pixmap') else None
            if lock_pix:
                lock_icon_lbl.setPixmap(lock_pix)
            else:
                # Fallback: draw a simple lock-like glyph using styled text
                lock_icon_lbl.setText('\u1F512')
                lock_icon_lbl.setAlignment(QtCore.Qt.AlignCenter)

            # Text content
            username = self.main_window.current_user['username'] if self.main_window and self.main_window.current_user else 'guest'
            role = self.main_window.current_user.get('role', 'guest') if self.main_window and self.main_window.current_user else 'guest'

            text_container = QtWidgets.QWidget()
            text_layout = QtWidgets.QVBoxLayout(text_container)
            text_layout.setContentsMargins(0, 0, 0, 0)
            title = QtWidgets.QLabel("Administrator Privileges Required")
            title.setStyleSheet("font-weight: bold; color: #ff9a3c; font-size: 13px;")
            details = QtWidgets.QLabel(
                "This section contains sensitive settings that require administrator privileges.\n"
                "Current user: {}  •  Role: {}".format(username, role)
            )
            details.setStyleSheet("color: #e6eef0; font-size: 11px;")
            details.setWordWrap(True)

            text_layout.addWidget(title)
            text_layout.addWidget(details)

            lock_card_layout.addWidget(lock_icon_lbl)
            lock_card_layout.addWidget(text_container, 1)

            # Inline style to ensure the card is visible on dark backgrounds
            lock_card.setStyleSheet(
                "background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2a2320, stop:1 #201816);"
                "border: 1px solid #3a2b28; border-radius: 8px;"
            )

            layout.addWidget(lock_card)
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
        self.tab_widget.addTab(tab, "Security Admin")

    def _build_labels_tab(self):
        """Build the Labels tab: read-only palette list, admin-gated Add/Edit/Delete."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        self.labels_table = QtWidgets.QTableWidget(0, 3)
        self.labels_table.setHorizontalHeaderLabels(["Color", "Name", "Meaning"])
        self.labels_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.labels_table)

        controls = QtWidgets.QHBoxLayout()
        self.add_label_button = QtWidgets.QPushButton("Add…")
        self.edit_label_button = QtWidgets.QPushButton("Edit…")
        self.delete_label_button = QtWidgets.QPushButton("Delete")
        for b in (self.add_label_button, self.edit_label_button, self.delete_label_button):
            controls.addWidget(b)
        layout.addLayout(controls)

        self.add_label_button.clicked.connect(self._on_add_label)
        self.delete_label_button.clicked.connect(self._on_delete_label)

        # State query only — must NOT call check_admin_permission() here, which
        # prompts (login/permission-denied dialogs) and would block widget
        # construction. Read the flag directly, as setup_security_tab and
        # MediaDisplayWidget._is_admin_user() already do.
        is_admin = bool(getattr(self.main_window, 'is_admin', False))
        for b in (self.add_label_button, self.edit_label_button, self.delete_label_button):
            b.setEnabled(is_admin)

        self._reload_labels()
        return tab

    def _reload_labels(self):
        """Repopulate labels_table from the DB's current palette."""
        labels = self.db.get_labels()
        self.labels_table.setRowCount(len(labels))
        for row, lbl in enumerate(labels):
            swatch = QtWidgets.QTableWidgetItem("")
            swatch.setBackground(QtGui.QBrush(QtGui.QColor(lbl["color_hex"])))
            self.labels_table.setItem(row, 0, swatch)
            self.labels_table.setItem(row, 1, QtWidgets.QTableWidgetItem(lbl["name"]))
            self.labels_table.setItem(row, 2, QtWidgets.QTableWidgetItem(lbl.get("meaning", "") or ""))

    def _create_label_row(self, name, color_hex, meaning):
        """Create a label, refresh the table, and notify listeners (e.g. open galleries)."""
        self.db.create_label(name, color_hex, meaning)
        self._reload_labels()
        self.settings_changed.emit()

    def _on_add_label(self):
        """Prompt for a name and color, then create the label.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission — which may
        prompt for login/permission — as the actual authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("add a label"):
            return
        name, ok = QtWidgets.QInputDialog.getText(self, "New label", "Name:")
        if not ok or not name:
            return
        color = QtWidgets.QColorDialog.getColor()
        if not color.isValid():
            return
        self._create_label_row(name, color.name(), "")

    def _on_delete_label(self):
        """Delete the selected label row, if any.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission as the actual
        authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("delete a label"):
            return
        row = self.labels_table.currentRow()
        if row < 0:
            return
        labels = self.db.get_labels()
        if row < len(labels):
            self.db.delete_label(labels[row]["label_id"])
            self._reload_labels()
            self.settings_changed.emit()

    def _build_search_tab(self):
        """Build the Search tab: read-only synonym/smart-collection lists,
        admin-gated Add/Delete controls."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        layout.addWidget(QtWidgets.QLabel("Synonyms (term → group)"))
        self.synonyms_table = QtWidgets.QTableWidget(0, 2)
        self.synonyms_table.setHorizontalHeaderLabels(["Term", "Group"])
        self.synonyms_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.synonyms_table)

        syn_controls = QtWidgets.QHBoxLayout()
        self.add_synonym_button = QtWidgets.QPushButton("Add…")
        self.delete_synonym_button = QtWidgets.QPushButton("Delete")
        syn_controls.addWidget(self.add_synonym_button)
        syn_controls.addWidget(self.delete_synonym_button)
        layout.addLayout(syn_controls)

        layout.addWidget(QtWidgets.QLabel("Smart Collections"))
        self.collections_table = QtWidgets.QTableWidget(0, 1)
        self.collections_table.setHorizontalHeaderLabels(["Name"])
        self.collections_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.collections_table)

        col_controls = QtWidgets.QHBoxLayout()
        self.delete_collection_button = QtWidgets.QPushButton("Delete collection")
        col_controls.addWidget(self.delete_collection_button)
        layout.addLayout(col_controls)

        self.add_synonym_button.clicked.connect(self._on_add_synonym)
        self.delete_synonym_button.clicked.connect(self._on_delete_synonym)
        self.delete_collection_button.clicked.connect(self._on_delete_collection)

        # State query only — must NOT call check_admin_permission() here, which
        # prompts (login/permission-denied dialogs) and would block widget
        # construction. Read the flag directly, as _build_labels_tab does.
        is_admin = bool(getattr(self.main_window, 'is_admin', False))
        for b in (self.add_synonym_button, self.delete_synonym_button, self.delete_collection_button):
            b.setEnabled(is_admin)

        self._reload_synonyms()
        self._reload_collections()
        return tab

    def _reload_synonyms(self):
        """Repopulate synonyms_table from the DB's current synonym list."""
        syns = self.db.get_synonyms()
        self.synonyms_table.setRowCount(len(syns))
        for row, s in enumerate(syns):
            self.synonyms_table.setItem(row, 0, QtWidgets.QTableWidgetItem(s["term"]))
            self.synonyms_table.setItem(row, 1, QtWidgets.QTableWidgetItem(s["group_key"]))

    def _reload_collections(self):
        """Repopulate collections_table from the DB's current smart collections."""
        cols = self.db.get_smart_collections()
        self.collections_table.setRowCount(len(cols))
        for row, c in enumerate(cols):
            self.collections_table.setItem(row, 0, QtWidgets.QTableWidgetItem(c["name"]))

    def _add_synonym_row(self, term, group_key):
        """Create a synonym, refresh the table, and notify listeners."""
        self.db.add_synonym(term, group_key)
        self._reload_synonyms()
        self.settings_changed.emit()

    def _on_add_synonym(self):
        """Prompt for a term and group key, then add the synonym.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission — which may
        prompt for login/permission — as the actual authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("add a synonym"):
            return
        term, ok = QtWidgets.QInputDialog.getText(self, "New synonym", "Term:")
        if not ok or not term:
            return
        group, ok2 = QtWidgets.QInputDialog.getText(self, "New synonym", "Group key:")
        if not ok2 or not group:
            return
        self._add_synonym_row(term, group)

    def _on_delete_synonym(self):
        """Delete the selected synonym row, if any.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission as the actual
        authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("delete a synonym"):
            return
        row = self.synonyms_table.currentRow()
        if row < 0:
            return
        syns = self.db.get_synonyms()
        if row < len(syns):
            self.db.delete_synonym(syns[row]["synonym_id"])
            self._reload_synonyms()
            self.settings_changed.emit()

    def _on_delete_collection(self):
        """Delete the selected smart collection row, if any.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission as the actual
        authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("delete a smart collection"):
            return
        row = self.collections_table.currentRow()
        if row < 0:
            return
        cols = self.db.get_smart_collections()
        if row < len(cols):
            self.db.delete_smart_collection(cols[row]["collection_id"])
            self._reload_collections()
            self.settings_changed.emit()

    def _build_accessibility_tab(self):
        """Build the Accessibility tab: high contrast, text scale, focus assist.

        This is a per-user preference, not an admin action (unlike Labels/
        Search), so there is no admin gate here. Controls load their
        current values from Config, and every change is persisted and
        re-applied to the live QApplication immediately -- it does not
        wait for "Save All Settings".
        """
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        group = QtWidgets.QGroupBox("Accessibility")
        form = QtWidgets.QFormLayout()

        self.a11y_high_contrast_checkbox = QtWidgets.QCheckBox("High contrast")
        self.a11y_high_contrast_checkbox.setChecked(bool(self.config.get('a11y_high_contrast', False)))
        form.addRow("High Contrast:", self.a11y_high_contrast_checkbox)

        self.a11y_text_scale_spin = QtWidgets.QSpinBox()
        self.a11y_text_scale_spin.setRange(100, 150)
        self.a11y_text_scale_spin.setSuffix(" %")
        self.a11y_text_scale_spin.setValue(int(self.config.get('a11y_text_scale', 100)))
        form.addRow("Text Scale:", self.a11y_text_scale_spin)

        self.a11y_focus_assist_checkbox = QtWidgets.QCheckBox("Focus assist (stronger focus outline)")
        self.a11y_focus_assist_checkbox.setChecked(bool(self.config.get('a11y_focus_assist', False)))
        form.addRow("Focus Assist:", self.a11y_focus_assist_checkbox)

        group.setLayout(form)
        layout.addWidget(group)

        hint = QtWidgets.QLabel("Changes are applied immediately and remembered across sessions.")
        hint.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        self.a11y_high_contrast_checkbox.toggled.connect(self._on_accessibility_changed)
        self.a11y_text_scale_spin.valueChanged.connect(self._on_accessibility_changed)
        self.a11y_focus_assist_checkbox.toggled.connect(self._on_accessibility_changed)

        return tab

    def _on_accessibility_changed(self, *_args):
        """Persist the three a11y_* preferences and re-apply them immediately.

        Accessibility is a user preference: write straight to Config (no
        admin gate, no "Save All Settings" round trip) and re-apply to the
        live target so the change is visible right away.

        Final review Finding 2: re-applying to `QApplication.instance()`
        unconditionally used to restyle the *entire* host application --
        inside Nuke that is Nuke's own QApplication, so toggling High
        contrast blacked out the whole DCC UI, not just StaX's. Use
        `self.accessibility_target` (set by the host at construction) when
        given; only fall back to the QApplication when none was provided
        (the standalone shell's behaviour, unchanged).
        """
        self.config.update({
            'a11y_high_contrast': self.a11y_high_contrast_checkbox.isChecked(),
            'a11y_text_scale': self.a11y_text_scale_spin.value(),
            'a11y_focus_assist': self.a11y_focus_assist_checkbox.isChecked(),
        })
        target = self.accessibility_target
        if target is None:
            target = QtWidgets.QApplication.instance()
        if target is not None:
            apply_accessibility(target, self.config)

    def _build_fields_tab(self):
        """Build the Metadata Fields tab: per-stack custom field list,
        admin-gated Add/Delete controls."""
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        layout.addWidget(QtWidgets.QLabel("Stack:"))
        self.fields_stack_combo = QtWidgets.QComboBox()
        for s in self.db.get_all_stacks():
            self.fields_stack_combo.addItem(s["name"], s["stack_id"])
        self.fields_stack_combo.currentIndexChanged.connect(
            lambda _i: self.select_fields_stack(self.fields_stack_combo.currentData()))
        layout.addWidget(self.fields_stack_combo)

        self.fields_table = QtWidgets.QTableWidget(0, 3)
        self.fields_table.setHorizontalHeaderLabels(["Key", "Label", "Type"])
        self.fields_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.fields_table)

        controls = QtWidgets.QHBoxLayout()
        self.add_field_button = QtWidgets.QPushButton("Add field…")
        self.delete_field_button = QtWidgets.QPushButton("Delete")
        controls.addWidget(self.add_field_button)
        controls.addWidget(self.delete_field_button)
        layout.addLayout(controls)

        self.add_field_button.clicked.connect(self._on_add_field)
        self.delete_field_button.clicked.connect(self._on_delete_field)

        # State query only — must NOT call check_admin_permission() here, which
        # prompts (login/permission-denied dialogs) and would block widget
        # construction. Read the flag directly, as _build_labels_tab and
        # _build_search_tab do.
        is_admin = bool(getattr(self.main_window, 'is_admin', False))
        for b in (self.add_field_button, self.delete_field_button):
            b.setEnabled(is_admin)

        self._fields_stack_id = None
        if self.fields_stack_combo.count():
            self.select_fields_stack(self.fields_stack_combo.itemData(0))
        return tab

    def select_fields_stack(self, stack_id):
        """Repopulate fields_table with the metadata fields defined for stack_id."""
        self._fields_stack_id = stack_id
        fields = self.db.get_metadata_fields(stack_id)
        self.fields_table.setRowCount(len(fields))
        for row, f in enumerate(fields):
            self.fields_table.setItem(row, 0, QtWidgets.QTableWidgetItem(f["key"]))
            self.fields_table.setItem(row, 1, QtWidgets.QTableWidgetItem(f["label"]))
            self.fields_table.setItem(row, 2, QtWidgets.QTableWidgetItem(f["field_type"]))

    def _on_add_field(self):
        """Prompt for key/label/type (and choices, if type is "choice"), then
        create the metadata field.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission — which may
        prompt for login/permission — as the actual authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("add a metadata field"):
            return
        key, ok = QtWidgets.QInputDialog.getText(self, "New field", "Key:")
        if not ok or not key:
            return
        label, ok2 = QtWidgets.QInputDialog.getText(self, "New field", "Label:")
        if not ok2:
            return
        ftype, ok3 = QtWidgets.QInputDialog.getItem(
            self, "New field", "Type:", ["text", "number", "choice", "date", "bool"], 0, False)
        if not ok3:
            return
        choices = None
        if ftype == "choice":
            raw, ok4 = QtWidgets.QInputDialog.getText(self, "Choices", "Comma-separated:")
            if not ok4:
                return
            choices = [c.strip() for c in raw.split(",") if c.strip()]
        self.db.create_metadata_field(self._fields_stack_id, key, label or key, ftype, choices=choices)
        self.select_fields_stack(self._fields_stack_id)
        self.settings_changed.emit()

    def _on_delete_field(self):
        """Delete the selected metadata field row, if any.

        Button is already gated for non-admins, but this is a real user action
        (they clicked), so re-check with check_admin_permission as the actual
        authorization gate.
        """
        if self.main_window and not self.main_window.check_admin_permission("delete a metadata field"):
            return
        row = self.fields_table.currentRow()
        if row < 0:
            return
        fields = self.db.get_metadata_fields(self._fields_stack_id)
        if row < len(fields):
            self.db.delete_metadata_field(fields[row]["field_id"])
            self.select_fields_stack(self._fields_stack_id)
            self.settings_changed.emit()

    def browse_database_path(self):
        """Browse for database file."""
        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Select Database File", self.db_path_edit.text(), "SQLite Database (*.db)"
        )
        if filename:
            self.db_path_edit.setText(filename)
    
    def browse_previews_path(self):
        """Browse for previews directory."""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Previews Directory", self.previews_path_edit.text()
        )
        if directory:
            self.previews_path_edit.setText(directory)
    
    def browse_blender_path(self):
        """Browse for Blender executable."""
        if not hasattr(self, 'blender_path_edit'):
            return

        caption = "Locate Blender executable"
        current_value = (self.blender_path_edit.text() or '').strip()
        start_dir = ''
        if current_value:
            if os.path.isdir(current_value):
                start_dir = current_value
            else:
                start_dir = os.path.dirname(current_value)

        if sys.platform.startswith('win'):
            filters = "Blender Executable (blender.exe);;Executable (*.exe);;All files (*.*)"
        else:
            filters = "All files (*)"

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            caption,
            start_dir,
            filters
        )
        if filename:
            self.blender_path_edit.setText(filename)

    def clear_blender_path(self):
        """Clear the Blender executable override."""
        if hasattr(self, 'blender_path_edit'):
            self.blender_path_edit.clear()

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
        from src.ui.dialogs import AddUserDialog
        dialog = AddUserDialog(self.db, self)
        if dialog.exec_():
            self.load_users_list()
            QtWidgets.QMessageBox.information(self, "Success", "User added successfully.")
    
    def edit_user(self):
        """Edit selected user."""
        from src.ui.dialogs import EditUserDialog
        current_row = self.users_list.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a user to edit.")
            return
        
        user_id = self.users_list.item(current_row, 0).data(QtCore.Qt.UserRole)
        dialog = EditUserDialog(self.db, user_id, self)
        if dialog.exec_():
            self.load_users_list()
    
    def deactivate_user(self):
        """Deactivate selected user."""
        current_row = self.users_list.currentRow()
        if current_row < 0:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a user to deactivate.")
            return
        
        user_id = self.users_list.item(current_row, 0).data(QtCore.Qt.UserRole)
        username = self.users_list.item(current_row, 0).text()
        
        # Prevent deactivating the logged-in user
        if self.main_window and self.main_window.current_user:
            if self.main_window.current_user.get('user_id') == user_id:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Cannot Deactivate",
                    "You cannot deactivate your own account."
                )
                return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deactivation",
            "Are you sure you want to deactivate user '{}'?".format(username),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                # Use update_user to set is_active=False instead of delete
                self.db.update_user(user_id, is_active=False)
                self.load_users_list()
                QtWidgets.QMessageBox.information(self, "Success", "User deactivated successfully.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to deactivate user: {}".format(str(e)))
    
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
    
    def on_gif_full_duration_toggled(self, checked):
        """Handle Full Duration checkbox toggle."""
        self.gif_duration.setEnabled(not checked)

    def on_auto_detect_sequences_toggled(self, checked):
        """Enable/disable sequence pattern selection based on auto-detect toggle."""
        if hasattr(self, 'sequence_pattern_combo') and self.sequence_pattern_combo:
            self.sequence_pattern_combo.setEnabled(checked)
        if hasattr(self, 'sequence_pattern_hint') and self.sequence_pattern_hint:
            self.sequence_pattern_hint.setEnabled(checked)
            if checked:
                self.update_sequence_pattern_hint(self.sequence_pattern_combo.currentText())
            else:
                self.sequence_pattern_hint.setText(
                    "Sequence detection disabled. Files will ingest individually even if their names share a pattern."
                )

    def update_sequence_pattern_hint(self, pattern):
        """Update the helper text under the pattern combo box."""
        if not hasattr(self, 'sequence_pattern_hint') or not self.sequence_pattern_hint:
            return

        examples = {
            '.####.ext': "Example: plate.1001.exr, plate.1002.exr",
            '_####.ext': "Example: plate_0001.dpx, plate_0002.dpx",
            ' ####.ext': "Example: render 1.png, render 2.png",
            '-####.ext': "Example: shot-10.jpg, shot-11.jpg"
        }
        sample = examples.get(pattern, "Example: image.####.exr")
        self.sequence_pattern_hint.setText(sample)
    
    def save_all_settings(self):
        """Save all settings to config and database."""
        # General settings
        self.config.set('database_path', self.db_path_edit.text())
        self.config.set('previews_path', self.previews_path_edit.text())
        self.config.set('user_name', self.user_name_edit.text())
        self.config.set('debug_mode', self.debug_mode_checkbox.isChecked())
        
        # Ingestion settings
        self.config.set('default_copy_policy', self.copy_policy.currentText())
        self.config.set('auto_detect_sequences', self.auto_detect.isChecked())
        self.config.set('sequence_pattern', self.sequence_pattern_combo.currentText())
        if hasattr(self, 'blender_path_edit'):
            blender_override = (self.blender_path_edit.text() or '').strip()
            self.config.set('blender_path', blender_override or None)
        
        # Preview settings
        self.config.set('generate_previews', self.gen_previews.isChecked())
        self.config.set('preview_size', self.preview_size.value())
        self.config.set('preview_quality', self.preview_quality.value())
        self.config.set('gif_size', self.gif_size.value())
        self.config.set('gif_fps', self.gif_fps.value())
        self.config.set('gif_duration', self.gif_duration.value())
        self.config.set('gif_full_duration', self.gif_full_duration.isChecked())
        self.config.set('ffmpeg_threads', self.ffmpeg_threads.value())
        self.config.set('show_entire_stack_elements', self.show_entire_stack.isChecked())
        
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

        # Persist database-aware settings
        self.config.save_to_database(self.db)

        # Ensure DebugManager reflects the latest preference immediately
        DebugManager.set_enabled(self.debug_mode_checkbox.isChecked())
        
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

            # Detach existing layout so setup_ui() can install a fresh root
            # layout without the Qt "already has a layout" warning (M13).
            old_layout = self.layout()
            if old_layout is not None:
                QtWidgets.QWidget().setLayout(old_layout)

            # Rebuild UI
            self.setup_ui()
            
            QtWidgets.QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")
            self.settings_changed.emit()


