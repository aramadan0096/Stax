# -*- coding: utf-8 -*-
"""
Blender Bridge
Abstraction layer for Blender API operations
"""

import os
import sys

try:
    import bpy
    BLENDER_AVAILABLE = True
except ImportError:
    BLENDER_AVAILABLE = False
    print("[BlenderBridge] WARNING: bpy module not available (mock mode)")


class BlenderBridge(object):
    """
    Bridge to Blender API with mock mode for development.
    All Blender operations go through this module to maintain abstraction.
    """
    
    def __init__(self, mock_mode=False):
        """
        Initialize Blender bridge.
        
        Args:
            mock_mode (bool): If True, use mock implementations. If False, use real Blender API.
        """
        self.mock_mode = mock_mode or not BLENDER_AVAILABLE
        self.bpy = bpy if BLENDER_AVAILABLE and not mock_mode else None
        
        if self.mock_mode:
            print("[BlenderBridge] Running in mock mode")
        else:
            print("[BlenderBridge] Running with real Blender API")
    
    def is_available(self):
        """Check if Blender API is available (not in mock mode)."""
        return not self.mock_mode and self.bpy is not None
    
    def import_mesh(self, filepath, node_name=None):
        """
        Import a mesh file into Blender scene.
        
        Args:
            filepath (str): Path to mesh file
            node_name (str): Optional name for the imported object
            
        Returns:
            object: Imported Blender object or None
        """
        if self.mock_mode:
            print("[MOCK] Import mesh: {}".format(filepath))
            return {'name': node_name or 'MockMesh'}
        
        try:
            # Determine file type and import accordingly
            ext = os.path.splitext(filepath)[1].lower()
            
            if ext == '.obj':
                self.bpy.ops.wm.obj_import(filepath=filepath)
            elif ext == '.fbx':
                self.bpy.ops.import_scene.fbx(filepath=filepath)
            elif ext == '.glb' or ext == '.gltf':
                self.bpy.ops.import_scene.gltf(filepath=filepath)
            elif ext == '.dae':
                self.bpy.ops.wm.collada_import(filepath=filepath)
            else:
                print("[BlenderBridge] WARNING: Unsupported mesh format: {}".format(ext))
                return None
            
            # Get the most recently imported object
            if self.bpy.context.selected_objects:
                obj = self.bpy.context.selected_objects[0]
                if node_name:
                    obj.name = node_name
                return obj
            
            return None
            
        except Exception as e:
            print("[BlenderBridge] ERROR: Failed to import mesh: {}".format(e))
            import traceback
            traceback.print_exc()
            return None
    
    def import_image(self, filepath, node_name=None):
        """
        Import an image as a texture/material.
        
        Args:
            filepath (str): Path to image file
            node_name (str): Optional name for the imported image
            
        Returns:
            object: Imported Blender image datablock or None
        """
        if self.mock_mode:
            print("[MOCK] Import image: {}".format(filepath))
            return {'name': node_name or 'MockImage'}
        
        try:
            # Load image
            img = self.bpy.data.images.load(filepath)
            if node_name:
                img.name = node_name
            return img
            
        except Exception as e:
            print("[BlenderBridge] ERROR: Failed to import image: {}".format(e))
            import traceback
            traceback.print_exc()
            return None
    
    def create_material(self, name, image_path=None):
        """
        Create a material with optional texture.
        
        Args:
            name (str): Material name
            image_path (str): Optional path to texture image
            
        Returns:
            object: Created material or None
        """
        if self.mock_mode:
            print("[MOCK] Create material: {}".format(name))
            return {'name': name}
        
        try:
            mat = self.bpy.data.materials.new(name=name)
            mat.use_nodes = True
            
            if image_path:
                img = self.import_image(image_path)
                if img:
                    # Add image texture node
                    nodes = mat.node_tree.nodes
                    tex_node = nodes.new('ShaderNodeTexImage')
                    tex_node.image = img
                    
                    # Connect to material output
                    output = nodes.get('Material Output')
                    if output:
                        mat.node_tree.links.new(tex_node.outputs['Color'], output.inputs['Base Color'])
            
            return mat
            
        except Exception as e:
            print("[BlenderBridge] ERROR: Failed to create material: {}".format(e))
            import traceback
            traceback.print_exc()
            return None
    
    def get_selected_objects(self):
        """
        Get currently selected objects.
        
        Returns:
            list: List of selected objects
        """
        if self.mock_mode:
            return []
        
        try:
            return list(self.bpy.context.selected_objects)
        except Exception as e:
            print("[BlenderBridge] ERROR: Failed to get selected objects: {}".format(e))
            return []
    
    def select_object(self, obj):
        """
        Select an object.
        
        Args:
            obj: Blender object to select
        """
        if self.mock_mode:
            print("[MOCK] Select object: {}".format(obj))
            return
        
        try:
            # Deselect all first
            self.bpy.ops.object.select_all(action='DESELECT')
            # Select the object
            obj.select_set(True)
            self.bpy.context.view_layer.objects.active = obj
        except Exception as e:
            print("[BlenderBridge] ERROR: Failed to select object: {}".format(e))
    
    def show_message(self, message, title="StaX"):
        """
        Show a message dialog.
        
        Args:
            message (str): Message text
            title (str): Dialog title
        """
        if self.mock_mode:
            print("[MOCK MESSAGE] {}: {}".format(title, message))
        else:
            try:
                # Use Blender's operator to show message
                self.bpy.ops.ui.report({'INFO'}, message)
            except Exception as e:
                print("[BlenderBridge] ERROR: Failed to show message: {}".format(e))
    
    def get_scene_objects(self):
        """
        Get all objects in the current scene.
        
        Returns:
            list: List of scene objects
        """
        if self.mock_mode:
            return []
        
        try:
            return list(self.bpy.context.scene.objects)
        except Exception as e:
            print("[BlenderBridge] ERROR: Failed to get scene objects: {}".format(e))
            return []


class BlenderIntegration(object):
    """High-level Blender integration functions using the BlenderBridge."""
    
    def __init__(self, blender_bridge, db_manager, config=None, ingestion_core=None, processor_manager=None):
        """Initialize Blender integration helpers."""
        self.bridge = blender_bridge
        self.db = db_manager
        self.config = config
        self.ingestion = ingestion_core
        self.processor_manager = processor_manager
        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    
    def insert_element(self, element_id, post_import_hook=None):
        """
        Insert an element into Blender scene based on its type.
        
        Args:
            element_id (int): Element ID to insert
            post_import_hook (callable): Optional post-import hook function
            
        Returns:
            object: Created Blender object or None
        """
        element = self.db.get_element_by_id(element_id)
        if not element:
            raise ValueError("Element not found: {}".format(element_id))
        
        # Determine which path to use
        filepath = element['filepath_hard'] if element['is_hard_copy'] else element['filepath_soft']
        
        # Resolve path
        if self.config:
            resolved_path = self.config.resolve_path(filepath, ensure_dir=False)
        else:
            resolved_path = filepath
        
        if not resolved_path or not os.path.exists(resolved_path):
            raise ValueError("File not found: {}".format(resolved_path))
        
        # Create appropriate object based on type
        obj = None
        
        if element['type'] == '3D':
            obj = self.bridge.import_mesh(resolved_path, node_name=element['name'])
        elif element['type'] == '2D':
            # For 2D elements, create a plane with the image as texture
            img = self.bridge.import_image(resolved_path, node_name=element['name'])
            if img:
                mat = self.bridge.create_material(element['name'], image_path=resolved_path)
                # Create plane and assign material
                if not self.bridge.mock_mode:
                    import bpy
                    bpy.ops.mesh.primitive_plane_add()
                    plane = bpy.context.active_object
                    plane.name = element['name']
                    if mat:
                        plane.data.materials.append(mat)
                    obj = plane
        
        # Execute post-import hook
        if post_import_hook and obj:
            try:
                post_import_hook(element, obj)
            except Exception as e:
                print("[BlenderIntegration] WARNING: Post-import hook failed: {}".format(e))
        
        return obj

