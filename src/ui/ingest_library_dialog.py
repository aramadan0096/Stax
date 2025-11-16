# -*- coding: utf-8 -*-
"""
Ingest Library Dialog
Dialog for bulk-ingesting folder structures
"""

import os
from PySide2 import QtWidgets, QtCore, QtGui
from src.icon_loader import get_icon

class IngestLibraryDialog(QtWidgets.QDialog):
    """Dialog for bulk-ingesting an existing library folder structure."""
    
    def __init__(self, db_manager, ingestion_core, config, parent=None):
        super(IngestLibraryDialog, self).__init__(parent)
        self.db = db_manager
        self.ingestion = ingestion_core
        self.config = config
        self.setWindowTitle("Ingest Library")
        self.resize(600, 400)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Instructions
        instructions = QtWidgets.QLabel(
            "<b>Bulk Library Ingestion</b><br/>"
            "This feature scans a folder hierarchy and automatically creates:<br/>"
            "- <b>Stacks</b> from top-level folders<br/>"
            "- <b>Lists</b> from subfolders<br/>"
            "- <b>Sub-Lists</b> from nested subfolders<br/>"
            "- Ingests all media files in each folder<br/><br/>"
            "<i>Example: ActionFX/explosions/aerial -> Stack: 'ActionFX', List: 'explosions', Sub-List: 'aerial'</i>"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("color: #cccccc; padding: 10px; background-color: #2a2a2a; border-radius: 5px;")
        layout.addWidget(instructions)
        
        # Folder selection
        folder_layout = QtWidgets.QHBoxLayout()
        folder_label = QtWidgets.QLabel("Library Folder:")
        folder_label.setStyleSheet("font-weight: bold;")
        self.folder_path_edit = QtWidgets.QLineEdit()
        self.folder_path_edit.setReadOnly(True)
        self.folder_path_edit.setPlaceholderText("Click 'Browse' to select library folder...")
        browse_btn = QtWidgets.QPushButton("Browse...")
        browse_btn.setObjectName('small')
        browse_btn.setProperty('class', 'small')
        browse_btn.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(folder_label)
        folder_layout.addWidget(self.folder_path_edit)
        folder_layout.addWidget(browse_btn)
        layout.addLayout(folder_layout)
        
        # Options group
        options_group = QtWidgets.QGroupBox("Ingestion Options")
        options_layout = QtWidgets.QFormLayout()
        
        # Stack/List prefix
        self.stack_prefix_edit = QtWidgets.QLineEdit()
        self.stack_prefix_edit.setPlaceholderText("Optional prefix (e.g., 'Studio_')")
        options_layout.addRow("Stack Prefix:", self.stack_prefix_edit)
        
        self.list_prefix_edit = QtWidgets.QLineEdit()
        self.list_prefix_edit.setPlaceholderText("Optional prefix (e.g., 'cat_')")
        options_layout.addRow("List Prefix:", self.list_prefix_edit)
        
        # Copy policy
        self.copy_policy_combo = QtWidgets.QComboBox()
        self.copy_policy_combo.addItems(["hard_copy", "soft_copy"])
        self.copy_policy_combo.setCurrentText(self.config.get('default_copy_policy', 'hard_copy'))
        options_layout.addRow("Copy Policy:", self.copy_policy_combo)
        
        # Max depth
        self.max_depth_spin = QtWidgets.QSpinBox()
        self.max_depth_spin.setMinimum(1)
        self.max_depth_spin.setMaximum(10)
        self.max_depth_spin.setValue(3)
        options_layout.addRow("Max Nesting Depth:", self.max_depth_spin)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Preview area (shows planned structure)
        preview_label = QtWidgets.QLabel("<b>Preview Structure:</b>")
        layout.addWidget(preview_label)
        
        self.preview_tree = QtWidgets.QTreeWidget()
        self.preview_tree.setHeaderLabels(["Name", "Type", "Media Files"])
        self.preview_tree.setAlternatingRowColors(True)
        self.preview_tree.setMaximumHeight(200)
        layout.addWidget(self.preview_tree)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.scan_btn = QtWidgets.QPushButton("Scan Folder")
        self.scan_btn.setObjectName('primary')
        self.scan_btn.setProperty('class', 'primary')
        self.scan_btn.clicked.connect(self.scan_folder)
        self.scan_btn.setEnabled(False)
        
        self.ingest_btn = QtWidgets.QPushButton("Start Ingestion")
        self.ingest_btn.setObjectName('primary')
        self.ingest_btn.setProperty('class', 'primary')
        self.ingest_btn.clicked.connect(self.start_ingestion)
        self.ingest_btn.setEnabled(False)
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setObjectName('small')
        cancel_btn.setProperty('class', 'small')
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.scan_btn)
        button_layout.addWidget(self.ingest_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Store scanned structure
        self.scanned_structure = None
    
    def select_folder(self):
        """Open folder selection dialog."""
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Library Folder", ""
        )
        
        if folder:
            self.folder_path_edit.setText(folder)
            self.scan_btn.setEnabled(True)
            self.preview_tree.clear()
            self.scanned_structure = None
            self.ingest_btn.setEnabled(False)
    
    def scan_folder(self):
        """Scan folder structure and show preview."""
        folder_path = self.folder_path_edit.text()
        if not folder_path or not os.path.exists(folder_path):
            QtWidgets.QMessageBox.warning(self, "Invalid Folder", "Please select a valid folder.")
            return
        
        # Show progress
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        
        try:
            # Scan structure
            self.scanned_structure = self._scan_directory_structure(
                folder_path,
                self.max_depth_spin.value()
            )
            
            # Display preview
            self._display_preview(self.scanned_structure)
            
            # Enable ingest button
            self.ingest_btn.setEnabled(True)
            
            QtWidgets.QMessageBox.information(
                self, "Scan Complete",
                "Found {} stacks, {} lists/sub-lists, {} media files".format(
                    len(self.scanned_structure),
                    sum(self._count_lists(stack) for stack in self.scanned_structure.values()),
                    sum(self._count_files(stack) for stack in self.scanned_structure.values())
                )
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Scan Error", "Failed to scan folder: {}".format(str(e)))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
    
    def _scan_directory_structure(self, root_path, max_depth):
        """
        Recursively scan directory structure.
        
        Returns:
            dict: {stack_name: {'lists': {list_name: {'sub_lists': {...}, 'files': [...]}, ...}, 'files': []}}
        """
        structure = {}
        
        # Get top-level folders (these become Stacks)
        for item in os.listdir(root_path):
            item_path = os.path.join(root_path, item)
            
            if os.path.isdir(item_path):
                stack_name = self.stack_prefix_edit.text() + item
                structure[stack_name] = {
                    'path': item_path,
                    'lists': {},
                    'files': []
                }
                
                # Scan Lists and Sub-Lists
                self._scan_lists_recursive(
                    item_path,
                    structure[stack_name]['lists'],
                    current_depth=1,
                    max_depth=max_depth
                )
                
                # Get media files in stack root
                structure[stack_name]['files'] = self._get_media_files(item_path)
        
        return structure
    
    def _scan_lists_recursive(self, folder_path, lists_dict, current_depth, max_depth):
        """Recursively scan lists and sub-lists."""
        if current_depth > max_depth:
            return
        
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            
            if os.path.isdir(item_path):
                list_name = self.list_prefix_edit.text() + item
                lists_dict[list_name] = {
                    'path': item_path,
                    'sub_lists': {},
                    'files': []
                }
                
                # Scan sub-lists
                self._scan_lists_recursive(
                    item_path,
                    lists_dict[list_name]['sub_lists'],
                    current_depth + 1,
                    max_depth
                )
                
                # Get media files
                lists_dict[list_name]['files'] = self._get_media_files(item_path)
    
    def _get_media_files(self, folder_path):
        """Get all media files in folder (non-recursive)."""
        media_extensions = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.exr', '.dpx', 
                           '.mp4', '.mov', '.avi', '.mkv', '.obj', '.fbx', '.abc', '.nk']
        
        media_files = []
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isfile(item_path):
                _, ext = os.path.splitext(item)
                if ext.lower() in media_extensions:
                    media_files.append(item_path)
        
        return media_files
    
    def _display_preview(self, structure):
        """Display scanned structure in tree widget."""
        self.preview_tree.clear()
        
        for stack_name, stack_data in structure.items():
            stack_item = QtWidgets.QTreeWidgetItem([
                stack_name, "Stack", str(len(stack_data['files']))
            ])
            # Use custom stack icon
            stack_icon = get_icon('stack', size=16)
            if stack_icon:
                stack_item.setIcon(0, stack_icon)
            stack_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#ff9a3c")))
            self.preview_tree.addTopLevelItem(stack_item)
            
            # Add lists
            self._add_lists_to_tree(stack_item, stack_data['lists'])
        
        self.preview_tree.expandAll()
    
    def _add_lists_to_tree(self, parent_item, lists_dict):
        """Recursively add lists to tree widget."""
        for list_name, list_data in lists_dict.items():
            list_item = QtWidgets.QTreeWidgetItem([
                list_name, "List", str(len(list_data['files']))
            ])
            # Use custom list icon
            list_icon = get_icon('list', size=16)
            if list_icon:
                list_item.setIcon(0, list_icon)
            list_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#16c6b0")))
            parent_item.addChild(list_item)
            
            # Add sub-lists recursively
            if list_data['sub_lists']:
                self._add_lists_to_tree(list_item, list_data['sub_lists'])
    
    def _count_lists(self, stack_data):
        """Count total lists in stack."""
        count = len(stack_data['lists'])
        for list_data in stack_data['lists'].values():
            count += self._count_sub_lists(list_data)
        return count
    
    def _count_sub_lists(self, list_data):
        """Count total sub-lists recursively."""
        count = len(list_data['sub_lists'])
        for sub_list_data in list_data['sub_lists'].values():
            count += self._count_sub_lists(sub_list_data)
        return count
    
    def _count_files(self, stack_data):
        """Count total files in stack."""
        count = len(stack_data['files'])
        for list_data in stack_data['lists'].values():
            count += self._count_files_in_list(list_data)
        return count
    
    def _count_files_in_list(self, list_data):
        """Count total files in list recursively."""
        count = len(list_data['files'])
        for sub_list_data in list_data['sub_lists'].values():
            count += self._count_files_in_list(sub_list_data)
        return count
    
    def start_ingestion(self):
        """Start bulk ingestion process."""
        if not self.scanned_structure:
            QtWidgets.QMessageBox.warning(self, "No Structure", "Please scan a folder first.")
            return
        
        # Confirm
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Ingestion",
            "Start bulk ingestion?\n\nThis will create Stacks/Lists and ingest all media files.\n"
            "This operation may take several minutes.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply != QtWidgets.QMessageBox.Yes:
            return
        
        # Count total files for progress
        total_files = sum(self._count_files(stack) for stack in self.scanned_structure.values())
        
        # Create progress dialog
        progress = QtWidgets.QProgressDialog("Ingesting library...", "Cancel", 0, total_files, self)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        
        success_count = 0
        error_count = 0
        processed = 0
        
        copy_policy = self.copy_policy_combo.currentText()
        
        try:
            # Process each stack
            for stack_name, stack_data in self.scanned_structure.items():
                if progress.wasCanceled():
                    break
                
                # Create stack
                stack_id = self.db.create_stack(stack_name, stack_data['path'])
                
                # Ingest stack files
                for filepath in stack_data['files']:
                    if progress.wasCanceled():
                        break
                    
                    progress.setValue(processed)
                    progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
                    
                    # Create temporary list for stack-level files
                    if not stack_data['lists']:
                        temp_list_id = self.db.create_list(stack_id, "_root")
                    
                    processed += 1
                
                # Process lists
                s, e, processed = self._ingest_lists_recursive(
                    stack_id, None, stack_data['lists'], copy_policy, progress, processed
                )
                success_count += s
                error_count += e
            
            progress.setValue(total_files)
            
            # Show result
            QtWidgets.QMessageBox.information(
                self, "Ingestion Complete",
                "Library ingested successfully!\n\n"
                "{} files ingested\n{} errors".format(success_count, error_count)
            )
            
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ingestion Error", "Failed: {}".format(str(e)))
    
    def _ingest_lists_recursive(self, stack_id, parent_list_id, lists_dict, copy_policy, progress, processed):
        """Recursively ingest lists and their files."""
        success_count = 0
        error_count = 0
        
        for list_name, list_data in lists_dict.items():
            if progress.wasCanceled():
                break
            
            # Create list
            list_id = self.db.create_list(stack_id, list_name, parent_list_id=parent_list_id)
            
            # Ingest files
            for filepath in list_data['files']:
                if progress.wasCanceled():
                    break
                
                progress.setValue(processed)
                progress.setLabelText("Ingesting: {}".format(os.path.basename(filepath)))
                
                result = self.ingestion.ingest_file(filepath, list_id, copy_policy=copy_policy)
                
                if result['success']:
                    success_count += 1
                else:
                    error_count += 1
                
                processed += 1
            
            # Process sub-lists
            s, e, processed = self._ingest_lists_recursive(
                stack_id, list_id, list_data['sub_lists'], copy_policy, progress, processed
            )
            success_count += s
            error_count += e
        
        return success_count, error_count, processed


