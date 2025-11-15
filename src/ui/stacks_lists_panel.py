# -*- coding: utf-8 -*-
"""
Stacks/Lists Navigation Panel
"""

import os
from PySide2 import QtWidgets, QtCore, QtGui

from src.icon_loader import get_icon, get_pixmap
from src.preview_cache import get_preview_cache
from src.ui.dialogs import (
    CreatePlaylistDialog,
    AddStackDialog,
    AddListDialog,
    AddSubListDialog,
)


class StacksListsPanel(QtWidgets.QWidget):
    """Left sidebar panel for Stacks, Lists, Favorites, and Playlists navigation."""
    
    # Signals
    stack_selected = QtCore.Signal(int)  # stack_id
    list_selected = QtCore.Signal(int)   # list_id
    favorites_selected = QtCore.Signal()  # Show favorites
    playlist_selected = QtCore.Signal(int)  # playlist_id
    
    def __init__(self, db_manager, config, parent=None):
        super(StacksListsPanel, self).__init__(parent)
        self.db = db_manager
        self.config = config
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup the UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title
        title = QtWidgets.QLabel("Navigation")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        title.setProperty("class", "title")
        layout.addWidget(title)
        
        # Favorites button
        self.favorites_btn = QtWidgets.QPushButton("Favorites")
        self.favorites_btn.setIcon(get_icon('favorite', size=20))
        self.favorites_btn.setProperty("class", "primary")
        self.favorites_btn.clicked.connect(self.on_favorites_clicked)
        layout.addWidget(self.favorites_btn)
        
        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator)
        
        # Playlists section
        playlists_header = QtWidgets.QHBoxLayout()
        playlists_label = QtWidgets.QLabel("Playlists")
        playlists_label.setStyleSheet("font-weight: bold; padding: 5px;")
        playlists_header.addWidget(playlists_label)
        
        self.add_playlist_btn = QtWidgets.QPushButton("New")
        self.add_playlist_btn.setIcon(get_icon('playlist', size=16))
        self.add_playlist_btn.setMaximumWidth(80)
        self.add_playlist_btn.clicked.connect(self.add_playlist)
        playlists_header.addWidget(self.add_playlist_btn)
        
        layout.addLayout(playlists_header)
        
        # Playlists list
        self.playlists_list = QtWidgets.QListWidget()
        self.playlists_list.setMaximumHeight(150)
        self.playlists_list.itemClicked.connect(self.on_playlist_clicked)
        layout.addWidget(self.playlists_list)
        
        # Separator
        separator2 = QtWidgets.QFrame()
        separator2.setFrameShape(QtWidgets.QFrame.HLine)
        separator2.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(separator2)
        
        # Stacks & Lists label
        stacks_label = QtWidgets.QLabel("Stacks & Lists")
        stacks_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(stacks_label)
        
        # Tree widget
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_tree_context_menu)
        layout.addWidget(self.tree)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        self.add_stack_btn = QtWidgets.QPushButton("Stack")
        self.add_stack_btn.setIcon(get_icon('stack', size=20))
        self.add_stack_btn.setToolTip("Add new Stack")
        self.add_stack_btn.clicked.connect(self.add_stack)
        button_layout.addWidget(self.add_stack_btn)
        
        self.add_list_btn = QtWidgets.QPushButton("List")
        self.add_list_btn.setIcon(get_icon('add', size=20))
        self.add_list_btn.setToolTip("Add new List")
        self.add_list_btn.clicked.connect(self.add_list)
        button_layout.addWidget(self.add_list_btn)
        
        layout.addLayout(button_layout)
    
    def on_favorites_clicked(self):
        """Handle favorites button click."""
        self.favorites_selected.emit()
    
    def on_playlist_clicked(self, item):
        """Handle playlist click."""
        playlist_id = item.data(QtCore.Qt.UserRole)
        if playlist_id:
            self.playlist_selected.emit(playlist_id)
    
    def add_playlist(self):
        """Add new playlist dialog."""
        dialog = CreatePlaylistDialog(self.db, self.config, self)
        if dialog.exec_():
            self.load_playlists()
    
    def load_playlists(self):
        """Load playlists from database."""
        self.playlists_list.clear()
        
        playlists = self.db.get_all_playlists()
        for playlist in playlists:
            item = QtWidgets.QListWidgetItem(playlist['name'])
            item.setIcon(get_icon('playlist', size=16))
            item.setData(QtCore.Qt.UserRole, playlist['playlist_id'])
            self.playlists_list.addItem(item)
    
    def load_data(self):
        """Load stacks, lists, and playlists from database with hierarchical sub-lists."""
        self.tree.clear()
        
        # Load playlists
        self.load_playlists()
        
        # Load stacks and lists
        stacks = self.db.get_all_stacks()
        for stack in stacks:
            stack_item = QtWidgets.QTreeWidgetItem([stack['name']])
            stack_item.setData(0, QtCore.Qt.UserRole, ('stack', stack['stack_id']))
            stack_item.setIcon(0, get_icon('stack', size=18))
            self.tree.addTopLevelItem(stack_item)
            
            # Load top-level lists for this stack (no parent)
            lists = self.db.get_lists_by_stack(stack['stack_id'], parent_list_id=None)
            for lst in lists:
                list_item = self._create_list_item(lst, stack['stack_id'])
                stack_item.addChild(list_item)
            
            stack_item.setExpanded(True)
    
    def _create_list_item(self, lst, stack_id):
        """
        Recursively create list item with sub-lists.
        
        Args:
            lst (dict): List data
            stack_id (int): Parent stack ID
            
        Returns:
            QTreeWidgetItem: Tree item with children
        """
        list_item = QtWidgets.QTreeWidgetItem([lst['name']])
        list_item.setData(0, QtCore.Qt.UserRole, ('list', lst['list_id'], stack_id))
        list_item.setIcon(0, get_icon('list', size=16))
        
        # Recursively load sub-lists
        sub_lists = self.db.get_sub_lists(lst['list_id'])
        for sub_lst in sub_lists:
            sub_item = self._create_list_item(sub_lst, stack_id)
            list_item.addChild(sub_item)
        
        return list_item
    
    def on_item_clicked(self, item, column):
        """Handle item click."""
        data = item.data(0, QtCore.Qt.UserRole)
        if data and len(data) >= 2:
            item_type = data[0]
            item_id = data[1]
            
            if item_type == 'stack':
                self.stack_selected.emit(item_id)
            elif item_type == 'list':
                self.list_selected.emit(item_id)
    
    def add_stack(self):
        """Add new stack dialog."""
        dialog = AddStackDialog(self.db, self)
        if dialog.exec_():
            self.load_data()
    
    def add_list(self):
        """Add new list or sub-list dialog."""
        # Get selected item
        current_item = self.tree.currentItem()
        stack_id = None
        list_id = None
        
        if current_item:
            data = current_item.data(0, QtCore.Qt.UserRole)
            if data and len(data) >= 2:
                item_type = data[0]
                item_id = data[1]
                
                if item_type == 'stack':
                    stack_id = item_id
                elif item_type == 'list':
                    # List is selected - offer to create sub-list
                    list_id = item_id
                    # Stack ID is the 3rd element if present, otherwise get from parent
                    if len(data) >= 3:
                        stack_id = data[2]
                    else:
                        parent = current_item.parent()
                        if parent:
                            parent_data = parent.data(0, QtCore.Qt.UserRole)
                            if parent_data and len(parent_data) >= 2:
                                stack_id = parent_data[1]
        
        # If a list is selected, create sub-list
        if list_id and stack_id:
            dialog = AddSubListDialog(self.db, list_id, stack_id, self)
            if dialog.exec_():
                self.load_data()
        else:
            # Otherwise, create top-level list
            dialog = AddListDialog(self.db, stack_id, self)
            if dialog.exec_():
                self.load_data()
    
    def show_tree_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        data = item.data(0, QtCore.Qt.UserRole)
        if not data:
            return
        
        menu = QtWidgets.QMenu(self)
        
        if len(data) >= 2:
            item_type = data[0]
            item_id = data[1]
            
            if item_type == 'stack':
                # Stack context menu
                add_list_action = menu.addAction(get_icon('add', size=16), "Add List")
                menu.addSeparator()
                delete_stack_action = menu.addAction(get_icon('delete', size=16), "Delete Stack")
                
                action = menu.exec_(self.tree.viewport().mapToGlobal(position))
                
                if action == add_list_action:
                    self.add_list_to_stack(item_id)
                elif action == delete_stack_action:
                    self.delete_stack(item_id)
                    
            elif item_type == 'list':
                # List context menu
                stack_id = data[2] if len(data) > 2 else None
                
                add_sublist_action = menu.addAction(get_icon('add', size=16), "Add Sub-List")
                menu.addSeparator()
                delete_list_action = menu.addAction(get_icon('delete', size=16), "Delete List")
                
                action = menu.exec_(self.tree.viewport().mapToGlobal(position))
                
                if action == add_sublist_action:
                    self.add_sub_list(item_id, stack_id)
                elif action == delete_list_action:
                    self.delete_list(item_id)
    
    def add_list_to_stack(self, stack_id):
        """Add a new list to a stack."""
        dialog = AddListDialog(self.db, stack_id, self)
        if dialog.exec_():
            self.load_data()
    
    def add_sub_list(self, parent_list_id, stack_id):
        """Add a sub-list under a parent list."""
        dialog = AddSubListDialog(self.db, parent_list_id, stack_id, self)
        if dialog.exec_():
            self.load_data()
    
    def delete_stack(self, stack_id):
        """Delete a stack after confirmation."""
        stack = self.db.get_stack_by_id(stack_id)
        if not stack:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete Stack '{}'?\n\nThis will delete ALL lists and elements in this stack.\n\nThis action cannot be undone.".format(stack['name']),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                self.db.delete_stack(stack_id)
                QtWidgets.QMessageBox.information(self, "Success", "Stack deleted successfully.")
                self.load_data()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete stack: {}".format(str(e)))
    
    def delete_list(self, list_id):
        """Delete a list after confirmation."""
        lst = self.db.get_list_by_id(list_id)
        if not lst:
            return
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            "Are you sure you want to delete List '{}'?\n\nThis will delete ALL sub-lists and elements in this list.\n\nThis action cannot be undone.".format(lst['name']),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            try:
                self.db.delete_list(list_id)
                QtWidgets.QMessageBox.information(self, "Success", "List deleted successfully.")
                self.load_data()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", "Failed to delete list: {}".format(str(e)))


