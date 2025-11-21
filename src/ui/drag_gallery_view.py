# -*- coding: utf-8 -*-
"""
Drag Gallery View Widget
Custom QListWidget with drag & drop support for Nuke integration
"""

import os

from PySide2 import QtWidgets, QtCore, QtGui

from src.ingestion_core import SequenceDetector


class DragGalleryView(QtWidgets.QListWidget):
    """Custom QListWidget with drag & drop support for Nuke integration."""
    
    def __init__(self, db_manager, config, nuke_bridge, parent=None):
        super(DragGalleryView, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.nuke_bridge = nuke_bridge
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        self.setDragEnabled(True)
        self.setAcceptDrops(False)  # We don't accept drops, only drag out

    def _resolve_storage_path(self, path_value):
        if not path_value:
            return None
        if os.path.isabs(path_value):
            return os.path.normpath(path_value)
        if self.config:
            resolved = self.config.resolve_path(path_value)
            if resolved:
                return os.path.normpath(resolved)
        return os.path.normpath(os.path.join(self._project_root, path_value))
    
    def startDrag(self, supportedActions):
        """Override startDrag to set custom mime data with element info."""
        selected_items = self.selectedItems()
        if not selected_items:
            return
        
        # Get element IDs from selected items
        element_ids = []
        for item in selected_items:
            element_id = item.data(QtCore.Qt.UserRole)
            if element_id:
                element_ids.append(element_id)
        
        if not element_ids:
            return
        
        # Create mime data with element information
        mime_data = QtCore.QMimeData()
        
        # Store element IDs as text (for external drops)
        mime_data.setText(','.join(str(eid) for eid in element_ids))
        
        # Create file paths list for elements
        file_paths = []
        for element_id in element_ids:
            element = self.db.get_element_by_id(element_id)
            if element:
                # Get appropriate file path (hard copy if exists, else soft copy)
                if element.get('is_hard_copy') and element.get('filepath_hard'):
                    resolved = self._resolve_storage_path(element['filepath_hard'])
                elif element.get('filepath_soft'):
                    resolved = self._resolve_storage_path(element['filepath_soft'])
                else:
                    resolved = None
                if resolved:
                    file_paths.append(resolved)
        
        # Set URL list for file paths (standard for drag & drop)
        urls = [QtCore.QUrl.fromLocalFile(path) for path in file_paths]
        mime_data.setUrls(urls)
        
        # Store custom data for internal processing
        mime_data.setData('application/x-stax-elements', ','.join(str(eid) for eid in element_ids).encode('utf-8'))
        
        # Create drag object
        drag = QtGui.QDrag(self)
        drag.setMimeData(mime_data)
        
        # Set drag icon (use first item's icon)
        if selected_items:
            pixmap = selected_items[0].icon().pixmap(64, 64)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QtCore.QPoint(32, 32))
        
        # Execute drag
        drag.exec_(QtCore.Qt.CopyAction | QtCore.Qt.MoveAction)
    
    def insert_to_nuke(self, element_ids):
        """
        Insert elements into Nuke as nodes.
        
        Args:
            element_ids (list): List of element IDs to insert
        """
        if not self.nuke_bridge.is_available():
            print("[MOCK] Would insert {} elements into Nuke".format(len(element_ids)))
        
        for element_id in element_ids:
            element = self.db.get_element_by_id(element_id)
            if not element:
                continue
            
            # Get file path
            if element.get('is_hard_copy') and element.get('filepath_hard'):
                filepath = element['filepath_hard']
            else:
                filepath = element.get('filepath_soft')
            
            resolved_path = self._resolve_storage_path(filepath)
            if not resolved_path:
                continue
            
            # Determine node type based on element type
            element_type = (element.get('type') or '2D').strip()
            element_type_lower = element_type.lower()
            
            if element_type_lower == '3d':
                # Create ReadGeo node for 3D assets
                self.nuke_bridge.create_read_geo_node(
                    resolved_path,
                    node_name=element['name']
                )
            elif element_type_lower == 'toolset':
                # Paste toolset (.nk file) into DAG
                self.nuke_bridge.paste_nodes_from_file(resolved_path)
            else:
                # Create Read node for 2D assets (images, sequences, videos)
                frame_range = None
                if element.get('frames'):
                    try:
                        frames = int(element['frames'])
                        if frames > 1:
                            # Detect frame range from sequence
                            frame_range = "1-{}".format(frames)
                    except (ValueError, TypeError):
                        pass
                if not frame_range:
                    frame_range = element.get('frame_range')

                if frame_range and '-' in frame_range:
                    sequence_info = SequenceDetector.detect_sequence(resolved_path, auto_detect=True)
                    if sequence_info:
                        pattern_path = SequenceDetector.get_sequence_path(sequence_info)
                        if pattern_path:
                            resolved_path = pattern_path

                self.nuke_bridge.create_read_node(
                    resolved_path,
                    frame_range=frame_range,
                    node_name=element['name']
                )
