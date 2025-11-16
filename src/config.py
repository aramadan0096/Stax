# -*- coding: utf-8 -*-
"""
Configuration Manager for StaX
Handles application settings and user preferences
Python 2.7 compatible
"""

import os
import json


class Config(object):
    """Application configuration manager."""
    
    DEFAULT_CONFIG = {
        # Database settings
        'database_path': './data/stax.db',
        
        # Repository settings
        'default_repository_path': './repository',
        
        # Preview settings
        'preview_dir': './previews',
        'previews_path': './previews',  # Configurable previews location
        'preview_size': 512,
        'preview_quality': 85,
        
        # GIF settings
        'gif_size': 256,
        'gif_fps': 10,
        'gif_duration': 3.0,
        
        # FFmpeg settings
        'ffmpeg_threads': 4,
        
        # Network/Database settings
        'db_max_retries': 10,
        'db_timeout': 60,
        
        # Performance/Caching settings
        'preview_cache_size': 200,
        'preview_cache_memory_mb': 200,
        'pagination_enabled': True,
        'items_per_page': 100,  # 50, 100, or 200
        'use_virtual_scrolling': True,
        'background_thumbnail_loading': True,
        
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
        
        # Check for STOCK_DB environment variable (overrides database_path and previews_path)
        stock_db_env = os.environ.get('STOCK_DB')
        if stock_db_env:
            self.config['database_path'] = stock_db_env
            # Derive previews path from database path (same directory, 'previews' subfolder)
            db_dir = os.path.dirname(stock_db_env)
            self.config['previews_path'] = os.path.join(db_dir, 'previews')
            self.config['preview_dir'] = os.path.join(db_dir, 'previews')  # Keep backward compatibility
            print("Using database from STOCK_DB environment variable: {}".format(stock_db_env))
            print("Using previews from derived path: {}".format(self.config['previews_path']))
        
        # Auto-detect user identity
        if self.config['machine_name'] is None:
            import socket
            self.config['machine_name'] = socket.gethostname()
        
        if self.config['user_name'] is None:
            self.config['user_name'] = os.environ.get('USERNAME') or os.environ.get('USER')
        
        # Load existing config if available
        if os.path.exists(config_path):
            self.load()
            
            # Re-apply STOCK_DB override after loading config
            if stock_db_env:
                self.config['database_path'] = stock_db_env
                db_dir = os.path.dirname(stock_db_env)
                self.config['previews_path'] = os.path.join(db_dir, 'previews')
                self.config['preview_dir'] = os.path.join(db_dir, 'previews')
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
    
    def load_from_database(self, db_manager):
        """
        Load configuration from database settings table.
        Database settings override config.json settings (except when STOCK_DB is set).
        
        Args:
            db_manager: DatabaseManager instance
        """
        try:
            # Get previews_path from database if available
            previews_path = db_manager.get_setting('previews_path')
            if previews_path:
                # Only apply if STOCK_DB is not set (environment variable takes precedence)
                if not os.environ.get('STOCK_DB'):
                    self.config['previews_path'] = previews_path
                    self.config['preview_dir'] = previews_path  # Backward compatibility
                    print("[Config] Loaded previews_path from database: {}".format(previews_path))
        except Exception as e:
            print("[Config] Warning: Could not load settings from database: {}".format(e))
    
    def save_to_database(self, db_manager):
        """
        Save previews_path configuration to database.
        
        Args:
            db_manager: DatabaseManager instance
        """
        try:
            # Only save if not controlled by STOCK_DB environment variable
            if not os.environ.get('STOCK_DB'):
                previews_path = self.config.get('previews_path')
                if previews_path:
                    db_manager.set_setting('previews_path', previews_path)
                    print("[Config] Saved previews_path to database: {}".format(previews_path))
        except Exception as e:
            print("[Config] Warning: Could not save settings to database: {}".format(e))
    
    def ensure_directories(self):
        """Ensure all configured directories exist."""
        # Get absolute paths to avoid permission issues with relative paths
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(script_dir)  # Go up one level from src/
        
        directories = [
            os.path.dirname(self.get('database_path')),
            self.get('default_repository_path'),
            self.get('preview_dir'),
            os.path.join(root_dir, 'logs')  # Add logs directory
        ]
        
        for directory in directories:
            if directory and not os.path.exists(directory):
                try:
                    # Convert relative paths to absolute paths
                    if not os.path.isabs(directory):
                        abs_directory = os.path.join(root_dir, directory)
                    else:
                        abs_directory = directory
                    
                    print("[Config] Creating directory: {}".format(abs_directory))
                    os.makedirs(abs_directory)
                    print("[Config]   [OK] Directory created successfully")
                except OSError as e:
                    print("[Config]   [WARN] Failed to create directory {}: {}".format(abs_directory, e))
                    print("[Config]   (Continuing - directory may not be needed immediately)")
                    # Don't raise - some directories might not be writable in Nuke context
