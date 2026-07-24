# -*- coding: utf-8 -*-
"""Minimal personalized start page (EP3 Task 11): Recent / Favorites /
Most-used sections, shown when no list is selected (see main.py wiring via
MediaDisplayWidget._set_empty_page_widget).

Design intent (spec §3.9 / §6): Most-used is expected to degrade
gracefully -- it depends on SP1's analytics tables/method landing, and on
there actually being insertion history yet, either of which can leave it
empty on a perfectly healthy DB. Recent/Favorites are plain element reads
against tables that have existed since day one, so a failure there is a
real DB problem and must not be swallowed the same way.
"""

import logging

from PySide2 import QtWidgets, QtCore

logger = logging.getLogger(__name__)


class StartPage(QtWidgets.QWidget):
    """Personalized landing page: Recent / Favorites / Most-used."""

    element_activated = QtCore.Signal(int)

    def __init__(self, db, user_name, machine_name, parent=None):
        super(StartPage, self).__init__(parent)
        self.db = db
        self.user_name = user_name
        self.machine_name = machine_name

        self._layout = QtWidgets.QVBoxLayout(self)
        self._recent_list = self._add_section("Recent")
        self._fav_list = self._add_section("Favorites")
        self._top_section, self._top_list = self._add_section("Most-used", return_box=True)

        self.refresh()

    def _add_section(self, title, return_box=False):
        box = QtWidgets.QGroupBox(title)
        v = QtWidgets.QVBoxLayout(box)
        lst = QtWidgets.QListWidget()
        lst.itemActivated.connect(self._on_activated)
        v.addWidget(lst)
        self._layout.addWidget(box)
        return (box, lst) if return_box else lst

    def _fill(self, lst, elements):
        lst.clear()
        for el in elements:
            item = QtWidgets.QListWidgetItem(el.get("name", ""))
            item.setData(QtCore.Qt.UserRole, el.get("element_id"))
            lst.addItem(item)

    def refresh(self):
        """Reload all three sections from the DB.

        Recent is a plain read against `elements` -- no table has ever
        existed here (SP1 or not), so it is not wrapped in a try/except;
        a real failure here should surface, not be hidden as "no recents".
        """
        self._fill(self._recent_list, self.db.get_recent_elements(12))

        try:
            favs = self.db.get_favorites(self.user_name, self.machine_name)
        except Exception:
            # Unlike Most-used, Favorites has no "this degrades gracefully
            # by design" story (spec §3.9/§6 only names Most-used) -- a
            # failure here is a real DB problem. It is still caught (a
            # widget shown at app startup should not take the whole window
            # down with it), but logged loudly with a traceback so it is
            # never silently mistaken for "the user has no favorites".
            logger.exception(
                "StartPage: get_favorites(%r, %r) failed, showing an empty "
                "Favorites section instead of the real data",
                self.user_name, self.machine_name,
            )
            favs = []
        self._fill(self._fav_list, favs)

        try:
            top = self.db.get_top_inserted_elements(10)
        except AttributeError:
            # SP1 (db_manager consolidation) may not have landed yet in
            # whatever environment this runs in -- Most-used degrading to
            # hidden is the documented, expected behaviour (spec §3.9/§6),
            # not an error worth a warning-level log.
            logger.info(
                "StartPage: db.get_top_inserted_elements is unavailable "
                "(SP1 not landed?); hiding Most-used section."
            )
            top = []
        except Exception as exc:
            logger.warning(
                "StartPage: get_top_inserted_elements failed, hiding "
                "Most-used section: %s", exc
            )
            top = []

        if top:
            self._fill(self._top_list, top)
            self._top_section.setVisible(True)
        else:
            self._top_section.setVisible(False)

    def recent_count(self):
        return self._recent_list.count()

    def _on_activated(self, item):
        eid = item.data(QtCore.Qt.UserRole)
        if eid is not None:
            self.element_activated.emit(eid)
