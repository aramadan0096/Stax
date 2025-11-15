# -*- coding: utf-8 -*-
"""
Extensibility Hooks for VFX_Asset_Hub
Defines custom processor architecture for pipeline integration
Python 2.7 compatible
"""

import os
import sys
import traceback


class ProcessorHook(object):
    """Base class for processor hooks with safe execution."""
    
    def __init__(self, script_path=None):
        """
        Initialize processor hook.
        
        Args:
            script_path (str): Path to user's Python script
        """
        self.script_path = script_path
        self.enabled = script_path is not None and os.path.exists(script_path)
    
    def execute(self, context):
        """
        Execute the processor hook with given context.
        
        Args:
            context (dict): Context dictionary passed to user script
            
        Returns:
            dict: Result from user script with keys:
                  - 'continue': bool (whether to continue operation)
                  - 'message': str (optional message)
                  - 'modified_context': dict (optionally modified context)
        """
        if not self.enabled:
            return {'continue': True, 'message': 'Hook not enabled'}
        
        try:
            # Create safe execution environment
            hook_globals = {
                '__builtins__': __builtins__,
                '__file__': self.script_path,
                '__name__': '__processor_hook__',
                'context': context
            }
            
            # Execute user script
            with open(self.script_path, 'r') as f:
                script_code = f.read()
            
            exec(script_code, hook_globals)
            
            # Extract result from hook_globals
            # User script should set 'result' variable
            result = hook_globals.get('result', {'continue': True})
            
            # Ensure result has required structure
            if not isinstance(result, dict):
                result = {'continue': True}
            
            if 'continue' not in result:
                result['continue'] = True
            
            return result
            
        except Exception as e:
            error_msg = "Hook execution failed: {}\n{}".format(
                str(e),
                traceback.format_exc()
            )
            print(error_msg)
            
            return {
                'continue': False,
                'message': error_msg,
                'error': True
            }


class PreIngestHook(ProcessorHook):
    """
    Pre-ingestion processor hook.
    Executed before file copy and metadata extraction.
    
    Context provided to user script:
        - source_path: str
        - name: str
        - type: str ('2D', '3D', 'Toolset')
        - is_sequence: bool
        - files: list (all files if sequence)
    
    User script should set 'result' variable with:
        - continue: bool (False to cancel ingestion)
        - message: str (optional message)
        - modified_context: dict (optionally modify context)
    
    Example user script:
        # Validate file naming convention
        import re
        
        if not re.match(r'^[A-Z]{3}_\d{4}', context['name']):
            result = {
                'continue': False,
                'message': 'File name does not match naming convention'
            }
        else:
            result = {'continue': True}
    """
    pass


class PostIngestHook(ProcessorHook):
    """
    Post-ingestion processor hook.
    Executed after asset is cataloged in database.
    
    Context provided to user script:
        - element_id: int
        - name: str
        - type: str
        - filepath_soft: str
        - filepath_hard: str
    
    Example user script:
        # Notify external asset management system
        import requests
        
        try:
            requests.post('http://asset-manager/api/notify', json={
                'element_id': context['element_id'],
                'name': context['name'],
                'path': context['filepath_hard'] or context['filepath_soft']
            })
            result = {'continue': True}
        except:
            result = {'continue': True, 'message': 'Failed to notify asset manager'}
    """
    pass


class PostImportHook(ProcessorHook):
    """
    Post-import processor hook.
    Executed after Nuke node is created in DAG.
    
    Context provided to user script:
        - element: dict (element data)
        - node: object (Nuke node)
        - filepath: str
    
    Example user script:
        # Apply OCIO colorspace automatically
        if context['element']['format'] in ['.exr', '.dpx']:
            try:
                node = context['node']
                if hasattr(node, 'knob'):
                    colorspace = node.knob('colorspace')
                    if colorspace:
                        colorspace.setValue('linear')
                result = {'continue': True}
            except:
                result = {'continue': True, 'message': 'Failed to set colorspace'}
        else:
            result = {'continue': True}
    """
    pass


class ProcessorManager(object):
    """
    Manages processor hooks for the application.
    Loads and executes user-defined processor scripts.
    """
    
    def __init__(self, config):
        """
        Initialize processor manager.
        
        Args:
            config (dict): Configuration with processor script paths
        """
        self.config = config
        
        # Initialize hooks
        self.pre_ingest = PreIngestHook(
            config.get('pre_ingest_processor')
        )
        self.post_ingest = PostIngestHook(
            config.get('post_ingest_processor')
        )
        self.post_import = PostImportHook(
            config.get('post_import_processor')
        )
    
    def reload_hooks(self):
        """Reload all hooks from configuration."""
        self.pre_ingest = PreIngestHook(
            self.config.get('pre_ingest_processor')
        )
        self.post_ingest = PostIngestHook(
            self.config.get('post_ingest_processor')
        )
        self.post_import = PostImportHook(
            self.config.get('post_import_processor')
        )
    
    def execute_pre_ingest(self, context):
        """Execute pre-ingest hook."""
        if self.pre_ingest.enabled:
            return self.pre_ingest.execute(context)
        return {'continue': True}
    
    def execute_post_ingest(self, context):
        """Execute post-ingest hook."""
        if self.post_ingest.enabled:
            return self.post_ingest.execute(context)
        return {'continue': True}
    
    def execute_post_import(self, context):
        """Execute post-import hook."""
        if self.post_import.enabled:
            return self.post_import.execute(context)
        return {'continue': True}
    
    def get_hook_status(self):
        """
        Get status of all hooks.
        
        Returns:
            dict: Status information for each hook
        """
        return {
            'pre_ingest': {
                'enabled': self.pre_ingest.enabled,
                'script_path': self.pre_ingest.script_path
            },
            'post_ingest': {
                'enabled': self.post_ingest.enabled,
                'script_path': self.post_ingest.script_path
            },
            'post_import': {
                'enabled': self.post_import.enabled,
                'script_path': self.post_import.script_path
            }
        }


# Example processor scripts for documentation

EXAMPLE_PRE_INGEST = """
# -*- coding: utf-8 -*-
# Example Pre-Ingest Processor
# Validates file naming and structure before ingestion

import re
import os

# Context contains:
# - source_path: str
# - name: str
# - type: str
# - is_sequence: bool
# - files: list

# Validate naming convention (e.g., must start with project code)
NAMING_PATTERN = r'^[A-Z]{3}_\\d{4}'

if not re.match(NAMING_PATTERN, context['name']):
    result = {
        'continue': False,
        'message': 'File name must match pattern: XXX_####'
    }
else:
    # Validation passed
    result = {
        'continue': True,
        'message': 'Validation passed'
    }
"""

EXAMPLE_POST_INGEST = """
# -*- coding: utf-8 -*-
# Example Post-Ingest Processor
# Sends notification to external tracking system

import json

# Context contains:
# - element_id: int
# - name: str
# - type: str
# - filepath_soft: str
# - filepath_hard: str

# Log to file or send to external system
log_entry = {
    'element_id': context['element_id'],
    'name': context['name'],
    'type': context['type']
}

print("Asset ingested: {}".format(json.dumps(log_entry)))

result = {'continue': True}
"""

EXAMPLE_POST_IMPORT = """
# -*- coding: utf-8 -*-
# Example Post-Import Processor
# Configures Nuke node after creation

# Context contains:
# - element: dict
# - node: object (Nuke node or mock)
# - filepath: str

# Apply colorspace for EXR files
if context['element']['format'] in ['.exr', '.dpx']:
    print("Setting colorspace to linear for {}".format(context['element']['name']))
    
    # In real Nuke environment:
    # if hasattr(context['node'], 'knob'):
    #     colorspace = context['node'].knob('colorspace')
    #     if colorspace:
    #         colorspace.setValue('linear')

result = {'continue': True}
"""
