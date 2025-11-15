# -*- coding: utf-8 -*-
"""
Configuration Manager for VFX_Asset_Hub
Handles application settings and user preferences
Python 2.7 compatible
"""

import os
import json


class Config(object):
    """Application configuration manager."""
    
    DEFAULT_CONFIG = {
        # Database settings
        'database_path': './data/vah.db',
        
        # Repository settings
        'default_repository_path': './repository',
        
        # Preview settings
        'preview_dir': './previews',
        'preview_size': 512,
        
        # Ingestion defaults
        'default_copy_policy': 'soft',  # 'soft' or 'hard'
        'auto_detect_sequences': True,
        'generate_previews': True,
        
        # Processor hooks
        'pre_ingest_processor': None,
        'post_ingest_processor': None,
        'post_import_processor': None,
        
        # GUI settings
        'default_view_mode': 'gallery',  # 'gallery' or 'list'
        'thumbnail_size': 256,
        'show_history_panel': False,
        'show_settings_panel': False,
        
        # Nuke integration
        'nuke_mock_mode': True,  # Use mock mode for development
        'auto_register_renderings': False,
        'default_render_target_list': None,
        
        # Search settings
        'search_match_type': 'loose',  # 'loose' or 'strict'
        
        # User identity (for favorites)
        'machine_name': None,  # Auto-detected if None
        'user_name': None,     # Auto-detected if None
    }
    
    def __init__(self, config_path='./config/config.json'):
        """
        Initialize configuration.
        
        Args:
            config_path (str): Path to configuration file
        """
        self.config_path = config_path
        self.config = self.DEFAULT_CONFIG.copy()
        
        # Auto-detect user identity
        if self.config['machine_name'] is None:
            import socket
            self.config['machine_name'] = socket.gethostname()
        
        if self.config['user_name'] is None:
            self.config['user_name'] = os.environ.get('USERNAME') or os.environ.get('USER')
        
        # Load existing config if available
        if os.path.exists(config_path):
            self.load()
        else:
            # Create default config file
            self.save()
    
    def load(self):
        """Load configuration from file."""
        try:
            with open(self.config_path, 'r') as f:
                loaded_config = json.load(f)
            
            # Merge with defaults (in case new keys were added)
            self.config.update(loaded_config)
            
            print("Configuration loaded from: {}".format(self.config_path))
        except Exception as e:
            print("Failed to load configuration: {}".format(e))
    
    def save(self):
        """Save configuration to file."""
        try:
            # Ensure config directory exists
            config_dir = os.path.dirname(self.config_path)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir)
            
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4, sort_keys=True)
            
            print("Configuration saved to: {}".format(self.config_path))
        except Exception as e:
            print("Failed to save configuration: {}".format(e))
    
    def get(self, key, default=None):
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set configuration value and save."""
        self.config[key] = value
        self.save()
    
    def update(self, updates):
        """Update multiple configuration values and save."""
        self.config.update(updates)
        self.save()
    
    def reset_to_defaults(self):
        """Reset configuration to defaults."""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()
    
    def get_all(self):
        """Get all configuration as dictionary."""
        return self.config.copy()
    
    def ensure_directories(self):
        """Ensure all configured directories exist."""
        directories = [
            os.path.dirname(self.get('database_path')),
            self.get('default_repository_path'),
            self.get('preview_dir')
        ]
        
        for directory in directories:
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
                print("Created directory: {}".format(directory))
