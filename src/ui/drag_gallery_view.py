# -*- coding: utf-8 -*-
"""
Drag Gallery View Widget
Custom QListWidget with drag & drop support for Nuke integration
"""

from PySide2 import QtWidgets, QtCore, QtGui

from src.ingestion_core import SequenceDetector


class DragGalleryView(QtWidgets.QListWidget):
    """Custom QListWidget with drag & drop support for Nuke integration."""
    
    def __init__(self, db_manager, nuke_bridge, parent=None):
        super(DragGalleryView, self).__init__(parent)
        self.db = db_manager
        self.nuke_bridge = nuke_bridge
        self.setDragEnabled(True)
        self.setAcceptDrops(False)  # We don't accept drops, only drag out
    
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
                    file_paths.append(element['filepath_hard'])
                elif element.get('filepath_soft'):
                    file_paths.append(element['filepath_soft'])
        
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
            
            if not filepath:
                continue
            
            # Determine node type based on element type
            element_type = element.get('type', '2D')
            
            if element_type == '3D':
                # Create ReadGeo node for 3D assets
                self.nuke_bridge.create_read_geo_node(
                    filepath,
                    node_name=element['name']
                )
            elif element_type == 'toolset':
                # Paste toolset (.nk file) into DAG
                self.nuke_bridge.paste_nodes_from_file(filepath)
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

                resolved_path = filepath
                if frame_range and '-' in frame_range:
                    sequence_info = SequenceDetector.detect_sequence(filepath, auto_detect=True)
                    if sequence_info:
                        pattern_path = SequenceDetector.get_sequence_path(sequence_info)
                        if pattern_path:
                            resolved_path = pattern_path

                self.nuke_bridge.create_read_node(
                    resolved_path,
                    frame_range=frame_range,
                    node_name=element['name']
                )
