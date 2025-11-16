# -*- coding: utf-8 -*-
"""
Nuke Bridge for StaX
Abstraction layer for Nuke API operations with mock implementations for development
Python 2.7 compatible
"""

import os

# Ensure bundled FFmpeg binaries are available when bridge runs outside standalone launcher
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_FFMPEG_BIN_DIR = os.path.join(_PROJECT_ROOT, 'bin', 'ffmpeg', 'bin')
if os.path.isdir(_FFMPEG_BIN_DIR):
    _existing_path = os.environ.get('PATH', '')
    _path_entries = _existing_path.split(os.pathsep) if _existing_path else []
    if _FFMPEG_BIN_DIR not in _path_entries:
        os.environ['PATH'] = _FFMPEG_BIN_DIR + (os.pathsep + _existing_path if _existing_path else '')


class NukeBridge(object):
    """
    Bridge to Nuke API with mock mode for development.
    All Nuke operations go through this module to maintain abstraction.
    """
    
    def __init__(self, mock_mode=True):
        """
        Initialize Nuke bridge.
        
        Args:
            mock_mode (bool): If True, use mock implementations. If False, use real Nuke API.
        """
        self.mock_mode = mock_mode
        self.nuke = None
        
        if not mock_mode:
            try:
                import nuke
                self.nuke = nuke
                self.mock_mode = False
            except ImportError:
                print("WARNING: Nuke module not found. Falling back to mock mode.")
                self.mock_mode = True
    
    def is_available(self):
        """Check if Nuke API is available (not in mock mode)."""
        return not self.mock_mode and self.nuke is not None
    
    def create_read_node(self, filepath, frame_range=None, node_name=None):
        """
        Create a Nuke Read node for 2D assets.
        
        Args:
            filepath (str): Path to image/sequence
            frame_range (str): Frame range (e.g., '1001-1150')
            node_name (str): Optional node name
            
        Returns:
            object: Nuke node object (or mock dict)
        """
        if self.mock_mode:
            # Mock implementation
            node = {
                'class': 'Read',
                'name': node_name or 'Read1',
                'file': filepath,
                'frame_range': frame_range,
                'created': True
            }
            print("[MOCK] Created Read node: {}".format(node_name or 'Read1'))
            print("       File: {}".format(filepath))
            if frame_range:
                print("       Frame range: {}".format(frame_range))
            return node
        else:
            # Real Nuke implementation
            node = self.nuke.nodes.Read(file=filepath)
            
            if node_name:
                node.setName(node_name)
            
            if frame_range:
                # Parse frame range
                parts = frame_range.split('-')
                if len(parts) == 2:
                    first = int(parts[0])
                    last = int(parts[1])
                    node['first'].setValue(first)
                    node['last'].setValue(last)
            
            return node
    
    def create_read_geo_node(self, filepath, node_name=None):
        """
        Create a Nuke ReadGeo node for 3D assets.
        
        Args:
            filepath (str): Path to 3D file (.abc, .obj, .fbx, etc.)
            node_name (str): Optional node name
            
        Returns:
            object: Nuke node object (or mock dict)
        """
        if self.mock_mode:
            # Mock implementation
            node = {
                'class': 'ReadGeo',
                'name': node_name or 'ReadGeo1',
                'file': filepath,
                'created': True
            }
            print("[MOCK] Created ReadGeo node: {}".format(node_name or 'ReadGeo1'))
            print("       File: {}".format(filepath))
            return node
        else:
            # Real Nuke implementation
            # Determine which ReadGeo variant to use based on extension
            ext = os.path.splitext(filepath)[1].lower()
            
            if ext == '.abc':
                node = self.nuke.nodes.ReadGeo2(file=filepath)
            else:
                node = self.nuke.nodes.ReadGeo(file=filepath)
            
            if node_name:
                node.setName(node_name)
            
            return node
    
    def paste_nodes_from_file(self, filepath):
        """
        Paste nodes from a .nk file (toolset).
        
        Args:
            filepath (str): Path to .nk file
            
        Returns:
            list: List of created nodes (or mock list)
        """
        if self.mock_mode:
            # Mock implementation
            nodes = [
                {'class': 'Unknown', 'name': 'ToolsetNode1', 'source': filepath}
            ]
            print("[MOCK] Pasted nodes from: {}".format(filepath))
            return nodes
        else:
            # Real Nuke implementation
            if not os.path.exists(filepath):
                raise IOError("Toolset file not found: {}".format(filepath))
            
            # Clear selection
            for n in self.nuke.selectedNodes():
                n.setSelected(False)
            
            # Paste nodes
            self.nuke.nodePaste(filepath)
            
            # Return newly pasted nodes (currently selected)
            return self.nuke.selectedNodes()
    
    def save_selected_as_toolset(self, output_path):
        """
        Save currently selected nodes as a toolset (.nk file).
        
        Args:
            output_path (str): Output .nk file path
            
        Returns:
            bool: True if successful
        """
        if self.mock_mode:
            # Mock implementation
            print("[MOCK] Saved selected nodes to: {}".format(output_path))
            # Create a dummy file
            with open(output_path, 'w') as f:
                f.write("# Mock Nuke toolset\n")
            return True
        else:
            # Real Nuke implementation
            selected = self.nuke.selectedNodes()
            if not selected:
                raise ValueError("No nodes selected")
            
            # Ensure directory exists
            output_dir = os.path.dirname(output_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Copy nodes to clipboard and save
            self.nuke.nodeCopy(output_path)
            return True
    
    def capture_node_graph_preview(self, output_path, width=512, height=512):
        """
        Capture a preview image of the node graph.
        
        Args:
            output_path (str): Output PNG file path
            width (int): Preview width in pixels
            height (int): Preview height in pixels
            
        Returns:
            bool: True if successful
        """
        if self.mock_mode:
            # Mock implementation - create a placeholder image
            print("[MOCK] Captured node graph preview to: {}".format(output_path))
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new('RGB', (width, height), color=(40, 40, 40))
                draw = ImageDraw.Draw(img)
                
                # Draw a simple representation
                draw.text((width//2 - 50, height//2), "Node Graph", fill=(255, 255, 255))
                
                img.save(output_path)
                return True
            except Exception as e:
                print("Mock preview generation failed: {}".format(str(e)))
                return False
        else:
            # Real Nuke implementation
            try:
                # Nuke doesn't have a built-in node graph capture API
                # This would require a custom screenshot or export method
                # For now, return False to indicate it's not available
                print("WARNING: Node graph preview capture not implemented for Nuke.")
                return False
            except Exception as e:
                print("Node graph preview failed: {}".format(str(e)))
                return False
    
    def get_selected_nodes(self):
        """
        Get currently selected nodes.
        
        Returns:
            list: List of selected nodes (or mock list)
        """
        if self.mock_mode:
            # Mock implementation
            return [
                {'class': 'Grade', 'name': 'Grade1'},
                {'class': 'Blur', 'name': 'Blur1'}
            ]
        else:
            return self.nuke.selectedNodes()
    
    def create_write_node(self, filepath, node_name=None):
        """
        Create a Nuke Write node.
        
        Args:
            filepath (str): Output file path
            node_name (str): Optional node name
            
        Returns:
            object: Nuke node object (or mock dict)
        """
        if self.mock_mode:
            # Mock implementation
            node = {
                'class': 'Write',
                'name': node_name or 'Write1',
                'file': filepath,
                'created': True
            }
            print("[MOCK] Created Write node: {}".format(node_name or 'Write1'))
            print("       File: {}".format(filepath))
            return node
        else:
            # Real Nuke implementation
            node = self.nuke.nodes.Write(file=filepath)
            
            if node_name:
                node.setName(node_name)
            
            return node
    
    def add_callback(self, callback_type, callback_func):
        """
        Add a callback to Nuke events.
        
        Args:
            callback_type (str): Type of callback ('onScriptSave', 'onScriptLoad', etc.)
            callback_func (callable): Callback function
            
        Returns:
            bool: True if successful
        """
        if self.mock_mode:
            # Mock implementation
            print("[MOCK] Added callback: {}".format(callback_type))
            return True
        else:
            # Real Nuke implementation
            self.nuke.addOnScriptSave(callback_func)
            return True
    
    def show_message(self, message, title="Stax"):
        """
        Show a message dialog.
        
        Args:
            message (str): Message text
            title (str): Dialog title
        """
        if self.mock_mode:
            print("[MOCK MESSAGE] {}: {}".format(title, message))
        else:
            self.nuke.message(message)
    
    def ask_user(self, question, title="Stax"):
        """
        Ask user a yes/no question.
        
        Args:
            question (str): Question text
            title (str): Dialog title
            
        Returns:
            bool: True if user answered yes
        """
        if self.mock_mode:
            print("[MOCK QUESTION] {}: {}".format(title, question))
            return True  # Default to yes in mock mode
        else:
            return self.nuke.ask(question)
    
    def get_frame_range(self):
        """
        Get the current script's frame range.
        
        Returns:
            tuple: (first_frame, last_frame)
        """
        if self.mock_mode:
            return (1001, 1100)
        else:
            root = self.nuke.root()
            return (int(root['first_frame'].value()), int(root['last_frame'].value()))


class NukeIntegration(object):
    """
    High-level Nuke integration functions using the NukeBridge.
    """
    
    def __init__(self, nuke_bridge, db_manager):
        """
        Initialize Nuke integration.
        
        Args:
            nuke_bridge (NukeBridge): NukeBridge instance
            db_manager: DatabaseManager instance
        """
        self.bridge = nuke_bridge
        self.db = db_manager
    
    def insert_element(self, element_id, post_import_hook=None):
        """
        Insert an element into Nuke DAG based on its type.
        
        Args:
            element_id (int): Element ID to insert
            post_import_hook (callable): Optional post-import hook function
            
        Returns:
            object: Created Nuke node
        """
        element = self.db.get_element_by_id(element_id)
        if not element:
            raise ValueError("Element not found: {}".format(element_id))
        
        # Determine which path to use
        filepath = element['filepath_hard'] if element['is_hard_copy'] else element['filepath_soft']
        
        if not filepath:
            raise ValueError("No valid filepath for element")
        
        # Create appropriate node based on type
        node = None
        
        if element['type'] == '2D':
            node = self.bridge.create_read_node(
                filepath=filepath,
                frame_range=element['frame_range'],
                node_name=element['name']
            )
        elif element['type'] == '3D':
            node = self.bridge.create_read_geo_node(
                filepath=filepath,
                node_name=element['name']
            )
        elif element['type'] == 'Toolset':
            nodes = self.bridge.paste_nodes_from_file(filepath)
            node = nodes[0] if nodes else None
        
        # Execute post-import hook
        if post_import_hook and node:
            post_import_hook({
                'element': element,
                'node': node,
                'filepath': filepath
            })
        
        return node
    
    def register_selection_as_toolset(self, name, target_list_id, comment=None, preview_path=None):
        """
        Save selected nodes as a toolset and register in database.
        
        Args:
            name (str): Toolset name
            target_list_id (int): Target list ID
            comment (str): Optional comment
            preview_path (str): Optional preview image path
            
        Returns:
            int: Created element ID
        """
        # Get target list info
        target_list = self.db.get_list_by_id(target_list_id)
        if not target_list:
            raise ValueError("Target list not found")
        
        stack = self.db.get_stack_by_id(target_list['stack_fk'])
        if not stack:
            raise ValueError("Stack not found")
        
        # Create output path
        toolset_dir = os.path.join(stack['path'], target_list['name'], 'toolsets')
        if not os.path.exists(toolset_dir):
            os.makedirs(toolset_dir)
        
        toolset_path = os.path.join(toolset_dir, "{}.nk".format(name))
        
        # Save toolset
        self.bridge.save_selected_as_toolset(toolset_path)
        
        # Create element in database
        element_id = self.db.create_element(
            list_id=target_list_id,
            name=name,
            element_type='Toolset',
            filepath_hard=toolset_path,
            is_hard_copy=True,
            format='.nk',
            comment=comment,
            preview_path=preview_path
        )
        
        # Log action
        self.db.log_ingestion(
            action='register_toolset',
            source_path='<selected_nodes>',
            target_list=target_list['name'],
            status='success',
            element_id=element_id
        )
        
        return element_id
