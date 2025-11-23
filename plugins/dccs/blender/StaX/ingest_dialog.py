# -*- coding: utf-8 -*-
"""
Ingest Dialog for Blender
Dialog to add selected objects to StaX library
"""

import os
import time
import hashlib
from PySide6 import QtWidgets, QtCore

class RegisterMeshDialog(QtWidgets.QDialog):
    """Dialog for registering selected Blender objects as a mesh asset."""
    
    def __init__(self, db_manager, blender_bridge, config, parent=None):
        super(RegisterMeshDialog, self).__init__(parent)
        self.db = db_manager
        self.bridge = blender_bridge
        self.config = config
        
        self.setWindowTitle("Add to Library (Mesh)")
        self.setMinimumWidth(500)
        self.setup_ui()
    
    def setup_ui(self):
        """Setup dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Info label
        info_label = QtWidgets.QLabel(
            "Export selected objects as Alembic (.abc) and register in StaX.\n"
            "A GLB proxy will also be generated for preview."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 11px; padding: 10px; background: #2a2a2a; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # Form layout
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        
        # Name
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("e.g., 'Hero Character'")
        form.addRow("Asset Name:", self.name_edit)
        
        # List selection
        self.list_combo = QtWidgets.QComboBox()
        self.load_lists()
        form.addRow("Save to List:", self.list_combo)
        
        # Comment
        self.comment_edit = QtWidgets.QTextEdit()
        self.comment_edit.setPlaceholderText("Optional description...")
        self.comment_edit.setMaximumHeight(80)
        form.addRow("Comment:", self.comment_edit)
        
        layout.addLayout(form)
        
        # Button box
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept_mesh)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_lists(self):
        """Load available lists into combo box."""
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            lists = self.db.get_lists_by_stack(stack['stack_id'])
            for lst in lists:
                self.list_combo.addItem(
                    "{} > {}".format(stack['name'], lst['name']),
                    lst['list_id']
                )
    
    def _sanitize_filename(self, name):
        import re
        safe = re.sub(r'[^A-Za-z0-9_\- ]+', '', name or '')
        safe = safe.strip().replace(' ', '_')
        return safe or 'Mesh'

    def accept_mesh(self):
        """Export and register mesh."""
        name = self.name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing Name", "Please enter an asset name.")
            return
        
        list_id = self.list_combo.currentData()
        if not list_id:
            QtWidgets.QMessageBox.warning(self, "No List", "Please select a list.")
            return
        
        # Check selection
        selected = self.bridge.get_selected_objects()
        if not selected:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select objects in Blender to export.")
            return

        try:
            # 1. Determine paths
            target_list = self.db.get_list_by_id(list_id)
            repository_path = self.db.get_repository_path_for_list(list_id)
            
            if not repository_path:
                raise ValueError(f"Repository path not configured for list '{target_list['name']}'")

            filename_stem = self._sanitize_filename(name)
            
            # Mesh path (Alembic)
            mesh_dir = os.path.join(repository_path, 'mesh') # Assuming 'mesh' subfolder convention
            abc_filename = f"{filename_stem}.abc"
            abc_path = os.path.join(mesh_dir, abc_filename)
            
            # Proxy path (GLB)
            proxy_dir = os.path.join(repository_path, 'proxy')
            glb_filename = f"{filename_stem}.glb"
            glb_path = os.path.join(proxy_dir, glb_filename)
            
            # 2. Export ABC
            if not self.bridge.export_abc(abc_path, selected_only=True):
                raise RuntimeError("Failed to export Alembic file.")
            
            # 3. Export GLB
            if not self.bridge.export_glb(glb_path, selected_only=True):
                print("Warning: Failed to export GLB proxy.")
                glb_path = None # Continue without proxy if it fails?
            
            # 4. Register in DB
            # Calculate relative paths
            stored_abc_path = self.config.make_relative(abc_path) if self.config else abc_path
            stored_glb_path = self.config.make_relative(glb_path) if glb_path and self.config else None
            
            file_size = os.path.getsize(abc_path) if os.path.exists(abc_path) else 0
            
            comment = self.comment_edit.toPlainText().strip()
            
            self.db.create_element(
                list_id=list_id,
                name=name,
                element_type='3D',
                filepath_soft=None,
                filepath_hard=stored_abc_path,
                is_hard_copy=True,
                format='.abc',
                comment=comment,
                geometry_preview_path=stored_glb_path,
                file_size=file_size
            )
            
            QtWidgets.QMessageBox.information(
                self,
                "Success",
                f"Mesh '{name}' added to library successfully!"
            )
            self.accept()
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error",
                f"Failed to add mesh: {str(e)}"
            )
