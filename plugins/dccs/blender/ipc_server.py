# -*- coding: utf-8 -*-
"""
IPC Server for Blender Plugin
Handles communication between StaX Core and Blender instance
Thread-safe command execution with main thread marshaling
"""

import os
import sys
import json
import socket
import threading
import traceback

# Python 2.7 vs 3.x compatibility
try:
    from Queue import Queue  # Python 2.7
except ImportError:
    from queue import Queue  # Python 3.x

try:
    from PySide2 import QtCore, QtWidgets
    PYSIDE_AVAILABLE = True
except ImportError:
    try:
        from PySide import QtCore, QtWidgets
        PYSIDE_AVAILABLE = True
    except ImportError:
        PYSIDE_AVAILABLE = False


class IPCCommandQueue(object):
    """Thread-safe command queue for marshaling commands to main thread."""
    
    def __init__(self):
        self._queue = Queue()
        self._results = {}  # Store results by command ID
        self._lock = threading.Lock()
        self._next_id = 0
    
    def enqueue(self, command, args=None, kwargs=None):
        """Enqueue a command for execution on main thread.
        
        Args:
            command (str): Command string to execute
            args (list): Optional positional arguments
            kwargs (dict): Optional keyword arguments
            
        Returns:
            int: Command ID for result retrieval
        """
        with self._lock:
            cmd_id = self._next_id
            self._next_id += 1
            
            self._queue.put({
                'id': cmd_id,
                'command': command,
                'args': args or [],
                'kwargs': kwargs or {}
            })
            return cmd_id
    
    def dequeue(self, timeout=0.1):
        """Dequeue next command (non-blocking).
        
        Args:
            timeout (float): Timeout in seconds
            
        Returns:
            dict or None: Command dict or None if queue empty
        """
        try:
            return self._queue.get(timeout=timeout)
        except:
            return None
    
    def set_result(self, cmd_id, result, error=None):
        """Set result for a command.
        
        Args:
            cmd_id (int): Command ID
            result: Result value
            error (str): Error message if any
        """
        with self._lock:
            self._results[cmd_id] = {
                'result': result,
                'error': error
            }
    
    def get_result(self, cmd_id, timeout=5.0):
        """Get result for a command (blocking).
        
        Args:
            cmd_id (int): Command ID
            timeout (float): Timeout in seconds
            
        Returns:
            dict: Result dict with 'result' and 'error' keys
        """
        import time
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if cmd_id in self._results:
                    return self._results.pop(cmd_id)
            time.sleep(0.01)
        return {'result': None, 'error': 'Timeout waiting for result'}


class IPCServer(object):
    """
    IPC Server for receiving commands from StaX Core.
    Listens on a TCP socket and executes commands safely on main thread.
    """
    
    def __init__(self, port=None, command_handler=None):
        """
        Initialize IPC Server.
        
        Args:
            port (int): Port to listen on (None = auto-assign based on PID)
            command_handler (callable): Function to handle command execution
        """
        self.port = port or self._get_default_port()
        self.command_handler = command_handler
        self.socket = None
        self.running = False
        self.server_thread = None
        self.command_queue = IPCCommandQueue()
        self._command_executor = None  # Will be set to main thread function
        
    def _get_default_port(self):
        """Get default port based on process ID to avoid collisions."""
        try:
            import os
            pid = os.getpid()
            # Use PID-based port in high range (49152-65535)
            base_port = 49152
            port = base_port + (pid % (65535 - base_port))
            return port
        except:
            return 55555  # Fallback port
    
    def start(self):
        """Start the IPC server in a background thread."""
        if self.running:
            return
        
        self.running = True
        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()
        
        # Write port to file for client discovery
        self._write_port_file()
    
    def stop(self):
        """Stop the IPC server."""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        if self.server_thread:
            self.server_thread.join(timeout=1.0)
    
    def _write_port_file(self):
        """Write port number to file for client discovery."""
        try:
            import tempfile
            port_file = os.path.join(tempfile.gettempdir(), 'stax_blender_port_{}.txt'.format(os.getpid()))
            with open(port_file, 'w') as f:
                f.write(str(self.port))
        except Exception as e:
            print("[IPCServer] Failed to write port file: {}".format(e))
    
    def _server_loop(self):
        """Main server loop running in background thread."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind(('localhost', self.port))
            self.socket.listen(5)
            self.socket.settimeout(1.0)  # Allow periodic checking of self.running
            
            print("[IPCServer] Listening on port {}".format(self.port))
            
            while self.running:
                try:
                    conn, addr = self.socket.accept()
                    # Handle connection in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(conn, addr),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print("[IPCServer] Error accepting connection: {}".format(e))
        except Exception as e:
            print("[IPCServer] Server error: {}".format(e))
            traceback.print_exc()
        finally:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
    
    def _handle_client(self, conn, addr):
        """Handle client connection in separate thread."""
        try:
            data = conn.recv(4096)
            if not data:
                return
            
            # Parse JSON command
            try:
                command_data = json.loads(data.decode('utf-8'))
            except Exception as e:
                response = {
                    'success': False,
                    'error': 'Invalid JSON: {}'.format(e)
                }
                conn.sendall(json.dumps(response).encode('utf-8'))
                return
            
            # Enqueue command for main thread execution
            cmd_id = self.command_queue.enqueue(
                command_data.get('command'),
                command_data.get('args', []),
                command_data.get('kwargs', {})
            )
            
            # Wait for result (with timeout)
            result = self.command_queue.get_result(cmd_id, timeout=30.0)
            
            # Send response
            response = {
                'success': result.get('error') is None,
                'result': result.get('result'),
                'error': result.get('error')
            }
            conn.sendall(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            print("[IPCServer] Error handling client: {}".format(e))
            traceback.print_exc()
            try:
                response = {
                    'success': False,
                    'error': str(e)
                }
                conn.sendall(json.dumps(response).encode('utf-8'))
            except:
                pass
        finally:
            try:
                conn.close()
            except:
                pass
    
    def set_command_executor(self, executor_func):
        """Set the function that will execute commands on main thread.
        
        Args:
            executor_func (callable): Function that takes (command, args, kwargs) and returns result
        """
        self._command_executor = executor_func
    
    def process_commands(self):
        """Process queued commands (call from main thread)."""
        if not self._command_executor:
            return
        
        # Process all queued commands
        while True:
            cmd = self.command_queue.dequeue(timeout=0.0)
            if not cmd:
                break
            
            try:
                # Execute command on main thread
                result = self._command_executor(
                    cmd['command'],
                    cmd['args'],
                    cmd['kwargs']
                )
                self.command_queue.set_result(cmd['id'], result)
            except Exception as e:
                error_msg = str(e)
                traceback.print_exc()
                self.command_queue.set_result(cmd['id'], None, error_msg)


class IPCClient(object):
    """
    IPC Client for sending commands from StaX Core to Blender.
    """
    
    @staticmethod
    def find_blender_port():
        """Find Blender's IPC server port by reading port file.
        
        Returns:
            int or None: Port number or None if not found
        """
        try:
            import tempfile
            import glob
            port_files = glob.glob(os.path.join(tempfile.gettempdir(), 'stax_blender_port_*.txt'))
            if port_files:
                # Get most recent file
                latest = max(port_files, key=os.path.getmtime)
                with open(latest, 'r') as f:
                    return int(f.read().strip())
        except Exception as e:
            print("[IPCClient] Error finding port: {}".format(e))
        return None
    
    @staticmethod
    def send_command(command, args=None, kwargs=None, port=None):
        """Send command to Blender IPC server.
        
        Args:
            command (str): Command string to execute
            args (list): Optional positional arguments
            kwargs (dict): Optional keyword arguments
            port (int): Port number (None = auto-detect)
            
        Returns:
            dict: Response with 'success', 'result', and 'error' keys
        """
        if port is None:
            port = IPCClient.find_blender_port()
        
        if port is None:
            return {
                'success': False,
                'error': 'Blender IPC server not found'
            }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect(('localhost', port))
            
            request = {
                'command': command,
                'args': args or [],
                'kwargs': kwargs or {}
            }
            
            sock.sendall(json.dumps(request).encode('utf-8'))
            
            # Receive response
            response_data = sock.recv(4096)
            sock.close()
            
            response = json.loads(response_data.decode('utf-8'))
            return response
            
        except Exception as e:
            return {
                'success': False,
                'error': 'Connection error: {}'.format(e)
            }

