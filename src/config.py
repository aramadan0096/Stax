# -*- coding: utf-8 -*-
"""
Configuration Manager for StaX
Handles application settings and user preferences
Python 2.7 compatible
"""

import os
import json
import errno


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

        # Diagnostics
        'debug_mode': True,
        
        # GIF settings
        'gif_size': 256,
        'gif_fps': 10,
        'gif_duration': 3.0,
    'gif_full_duration': False,
    'gif_max_frames': 24,
    'gif_loop_forever': True,
        
        # FFmpeg settings
        'ffmpeg_threads': 4,
    'sequence_preview_fps': 24,
        
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
        'sequence_pattern': '.####.ext',
        'generate_previews': True,
    'blender_path': None,
        
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
        # Project root (two levels up from this file: src/..)
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config = self.DEFAULT_CONFIG.copy()
        
        # Valid sequence pattern choices
        self.sequence_patterns = ['.####.ext', '_####.ext', ' ####.ext', '-####.ext']

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

        # Ensure sequence pattern is valid
        if self.config.get('sequence_pattern') not in self.sequence_patterns:
            self.config['sequence_pattern'] = '.####.ext'

        self._apply_debug_mode(self.config.get('debug_mode', True))
    
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
        if key == 'debug_mode':
            self._apply_debug_mode(value)
    
    def update(self, updates):
        """Update multiple configuration values and save."""
        self.config.update(updates)
        self.save()
        if 'debug_mode' in updates:
            self._apply_debug_mode(updates.get('debug_mode'))
    
    def reset_to_defaults(self):
        """Reset configuration to defaults."""
        self.config = self.DEFAULT_CONFIG.copy()
        self.save()
        self._apply_debug_mode(self.config.get('debug_mode', True))
    
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

            blender_setting = db_manager.get_setting('blender_path')
            if blender_setting is not None and blender_setting != '':
                self.config['blender_path'] = blender_setting
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

            blender_setting = self.config.get('blender_path')
            if blender_setting is not None:
                db_manager.set_setting('blender_path', blender_setting or '')
                print("[Config] Saved blender_path to database")
        except Exception as e:
            print("[Config] Warning: Could not save settings to database: {}".format(e))
    
    def ensure_directories(self):
        """Ensure all configured directories exist."""
        # Get absolute paths to avoid permission issues with relative paths
        root_dir = self.root_dir

        directories = []

        db_path = self.get('database_path')
        if db_path:
            directories.append(os.path.dirname(self.resolve_path(db_path)))

        repository_path = self.get('default_repository_path')
        if repository_path:
            directories.append(self.resolve_path(repository_path, treat_as_dir=True))

        preview_dir = self.get('preview_dir')
        if preview_dir:
            directories.append(self.resolve_path(preview_dir, treat_as_dir=True))

        previews_path = self.get('previews_path')
        if previews_path and previews_path != preview_dir:
            directories.append(self.resolve_path(previews_path, treat_as_dir=True))

        directories.append(os.path.join(root_dir, 'logs'))  # Add logs directory

        seen = set()
        for directory in directories:
            if not directory:
                continue
            # Normalise and deduplicate
            normalised = os.path.normpath(directory)
            if normalised in seen:
                continue
            seen.add(normalised)

            if not os.path.exists(normalised):
                try:
                    print("[Config] Creating directory: {}".format(normalised))
                    os.makedirs(normalised)
                    print("[Config]   [OK] Directory created successfully")
                except OSError as e:
                    if e.errno != errno.EEXIST:
                        print("[Config]   [WARN] Failed to create directory {}: {}".format(normalised, e))
                        print("[Config]   (Continuing - directory may not be needed immediately)")
                    # Don't raise - some directories might not be writable in Nuke context

    def resolve_path(self, path, ensure_dir=False, treat_as_dir=None):
        """Resolve a possibly relative path to an absolute path rooted at project."""
        if not path:
            return None
        resolved = path
        if not os.path.isabs(path):
            resolved = os.path.normpath(os.path.join(self.root_dir, path))
        else:
            resolved = os.path.normpath(path)

        if ensure_dir:
            directory = resolved
            if treat_as_dir is False or (treat_as_dir is None and os.path.splitext(resolved)[1]):
                directory = os.path.dirname(resolved)
            if directory and not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except OSError as error:
                    if error.errno != errno.EEXIST:
                        raise
        return resolved

    def make_relative(self, path):
        """Return path relative to project root when possible."""
        if not path:
            return None
        path = os.path.normpath(path)
        try:
            relative = os.path.relpath(path, self.root_dir)
        except ValueError:
            return path.replace('\\', '/').replace('\\', '/')
        if relative.startswith('..'):
            return path.replace('\\', '/').replace('\\', '/')
        return relative.replace('\\', '/').replace('\\', '/')

    def _apply_debug_mode(self, value):
        """Update global debug manager with current setting."""
        try:
            from src.debug_manager import DebugManager
            DebugManager.set_enabled(bool(value))
        except Exception:
            pass
