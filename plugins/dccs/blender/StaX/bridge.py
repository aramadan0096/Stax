# -*- coding: utf-8 -*-
"""
Blender Bridge for StaX
Abstraction layer for Blender API operations
Python 3 compatible (Blender 2.8+)
"""

import os
import sys
import bpy

class BlenderBridge(object):
    """
    Bridge to Blender API.
    """
    
    def __init__(self):
        pass
    
    def is_available(self):
        """Check if Blender API is available."""
        return True
    
    def import_abc(self, filepath):
        """
        Import Alembic file.
        
        Args:
            filepath (str): Path to .abc file
        """
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return False
            
        try:
            bpy.ops.wm.alembic_import(filepath=filepath)
            return True
        except Exception as e:
            print(f"Failed to import Alembic: {e}")
            return False

    def import_object(self, filepath):
        """
        Import 3D object based on extension.
        """
        ext = os.path.splitext(filepath)[1].lower()
        if ext == '.abc':
            return self.import_abc(filepath)
        elif ext == '.fbx':
            try:
                bpy.ops.import_scene.fbx(filepath=filepath)
                return True
            except Exception as e:
                print(f"Failed to import FBX: {e}")
                return False
        elif ext == '.obj':
            try:
                bpy.ops.import_scene.obj(filepath=filepath)
                return True
            except Exception as e:
                print(f"Failed to import OBJ: {e}")
                return False
        elif ext in ['.glb', '.gltf']:
            try:
                bpy.ops.import_scene.gltf(filepath=filepath)
                return True
            except Exception as e:
                print(f"Failed to import GLTF: {e}")
                return False
        else:
            print(f"Unsupported format: {ext}")
            return False

    def create_read_geo_node(self, filepath, node_name=None):
        """
        Import 3D object (matches NukeBridge interface).
        """
        success = self.import_object(filepath)
        # Return a dummy object or the imported object(s) if possible
        # DragGalleryView doesn't use the return value much, just checks if it worked?
        # Actually it returns 'node'.
        return success

    def create_read_node(self, filepath, frame_range=None, node_name=None):
        """
        Import 2D element (matches NukeBridge interface).
        For Blender, we might import as Image Plane or Reference Image.
        """
        # TODO: Implement image import if needed. For now, just print.
        print(f"Importing 2D element: {filepath}")
        # Example: bpy.ops.import_image.to_plane(files=[{'name': os.path.basename(filepath)}], directory=os.path.dirname(filepath))
        return None

    def paste_nodes_from_file(self, filepath):
        """
        Paste toolset (matches NukeBridge interface).
        For Blender, maybe append from .blend file?
        """
        print(f"Pasting/Appending from: {filepath}")
        return None


    def export_abc(self, filepath, selected_only=True):
        """
        Export selected objects to Alembic.
        """
        try:
            # Ensure directory exists
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
                
            bpy.ops.wm.alembic_export(
                filepath=filepath,
                selected=selected_only,
                flatten=False,
                uvs=True,
                packuv=True,
                face_sets=True,
                subdiv_schema=False,
                apply_subdiv=False,
                compression_type='OGAWA',
                global_scale=1.0,
                end=bpy.context.scene.frame_end,
                start=bpy.context.scene.frame_start
            )
            return True
        except Exception as e:
            print(f"Failed to export Alembic: {e}")
            return False

    def export_glb(self, filepath, selected_only=True):
        """
        Export selected objects to GLB (glTF binary).
        """
        try:
            # Ensure directory exists
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)

            bpy.ops.export_scene.gltf(
                filepath=filepath,
                use_selection=selected_only,
                export_format='GLB',
                export_apply=True  # Apply modifiers
            )
            return True
        except Exception as e:
            print(f"Failed to export GLB: {e}")
            return False
