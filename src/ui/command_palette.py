# -*- coding: utf-8 -*-
"""Command palette: harvest live actions + a small extra-command registry (EP3)."""

import difflib


def harvest_actions(menu_bar, toolbar):
    """Collect leaf (label, QAction) pairs from a menu bar and toolbar."""
    entries = []
    seen = set()

    def walk(actions):
        for a in actions:
            if a.isSeparator() or not a.text():
                continue
            sub = a.menu()
            if sub is not None:
                walk(sub.actions())
            elif id(a) not in seen:
                seen.add(id(a))
                entries.append((a.text().replace("&", ""), a))

    if menu_bar is not None:
        walk(menu_bar.actions())
    if toolbar is not None:
        walk(toolbar.actions())
    return entries


class CommandRegistry(object):
    """Extra palette commands: (label, callable)."""

    def __init__(self):
        self._items = []

    def register(self, label, callback):
        self._items.append((label, callback))

    def clear(self):
        self._items = []

    def entries(self):
        return list(self._items)


def _subsequence(query, text):
    it = iter(text)
    return all(ch in it for ch in query)


def fuzzy_filter(query, labels):
    """Return indices of labels matching query, best match first."""
    q = (query or "").strip().lower()
    if not q:
        return list(range(len(labels)))
    scored = []
    for i, label in enumerate(labels):
        low = label.lower()
        if q in low:
            score = 100 - low.index(q)
        elif _subsequence(q, low):
            score = 50 * difflib.SequenceMatcher(None, q, low).ratio()
        else:
            continue
        scored.append((score, i))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [i for _, i in scored]
