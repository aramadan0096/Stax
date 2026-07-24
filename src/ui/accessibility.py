# -*- coding: utf-8 -*-
"""Accessibility application: text scale, high contrast, focus assist (EP3).

Applies three user-facing preferences, stored in `Config` under the
``a11y_*`` keys, on top of StaX's existing dark theme:

- ``a11y_high_contrast`` (bool)  -- swap in a high-contrast QSS overlay
- ``a11y_text_scale``    (int, 100-150) -- app-wide font point-size multiplier
- ``a11y_focus_assist``  (bool)  -- stronger focus-ring QSS overlay

Design note (EP3 spec Sections 3.7 / 6): accessibility must be layered on
as an ADDITIVE QSS overlay plus a font-size multiplier -- never by
replacing the base stylesheet/font outright -- so it does not fight the
real dark theme (`resources/style.qss`, applied via `app.setStyleSheet()`
in `main.py`'s STEP 3) and stays idempotent across repeated calls.

Idempotence requires scaling from the pre-accessibility baseline (the
font size and stylesheet as they were *before this module ever touched
them*), not from the app's current, possibly-already-scaled state --
otherwise re-applying the same 150% scale twice would compound to 225%,
and toggling settings back to 100% would never restore the original
values. To do that without stashing private state on the shared `Config`
object (it is a JSON-backed settings store, not a scratch pad), this
module keeps its own small per-QApplication cache, keyed by `id(app)`.
"""

import logging

logger = logging.getLogger(__name__)

_HIGH_CONTRAST_QSS = """
QWidget { background: #000000; color: #FFFFFF; }
QLineEdit, QListWidget, QTableWidget { background: #101010; color: #FFFFFF; }
"""

_FOCUS_QSS = """
*:focus { border: 2px solid #4C9AFF; }
"""

# id(app) -> {"base_pt": int, "base_qss": str}: each QApplication's
# pre-accessibility baseline, captured once and reused on every later call
# so repeated/round-tripped calls never compound. Process-local cache, not
# persisted -- intentionally lost on restart, when apply_accessibility()
# at startup captures a fresh baseline from the just-built base theme.
_baseline_cache = {}


def scaled_point_size(base_pt, scale_percent):
    """Return base_pt scaled by scale_percent (e.g. 150 -> 1.5x), rounded to int."""
    return int(round(base_pt * (scale_percent / 100.0)))


def reset_cache(app=None):
    """Drop cached baseline(s) so the next apply_accessibility() call
    re-captures the app's *current* font/stylesheet as the new baseline.

    Intended for tests (each test wants its own clean baseline) and for
    the rare legitimate case of intentionally re-basing (e.g. the base
    theme itself changed at runtime). Not used by normal app startup.
    """
    if app is None:
        _baseline_cache.clear()
    else:
        _baseline_cache.pop(id(app), None)


def _get_baseline(app):
    """Return the cached pre-accessibility baseline for app, capturing it
    from the app's current state the first time this app instance is seen."""
    key = id(app)
    baseline = _baseline_cache.get(key)
    if baseline is None:
        font = app.font()
        base_pt = font.pointSize() if font.pointSize() > 0 else 9
        baseline = {"base_pt": base_pt, "base_qss": app.styleSheet()}
        _baseline_cache[key] = baseline
    return baseline


def apply_accessibility(app, config):
    """Apply the three ``a11y_*`` preferences from config to app.

    Safe to call repeatedly (on every settings change, and once at
    startup): each call re-derives the full result from the cached
    pre-accessibility baseline plus the current config, so it is
    idempotent -- applying the same settings twice is a no-op beyond the
    first call, and returning settings to their defaults restores the
    exact original font size and stylesheet.

    No-ops if app is None (e.g. no QApplication instance available).
    """
    if app is None:
        return

    high_contrast = bool(config.get("a11y_high_contrast", False))
    text_scale = int(config.get("a11y_text_scale", 100))
    focus_assist = bool(config.get("a11y_focus_assist", False))

    baseline = _get_baseline(app)

    font = app.font()
    font.setPointSize(scaled_point_size(baseline["base_pt"], text_scale))
    app.setFont(font)

    qss = ""
    if high_contrast:
        qss += _HIGH_CONTRAST_QSS
    if focus_assist:
        qss += _FOCUS_QSS
    # Layer on top of the real base stylesheet -- never discard it.
    app.setStyleSheet(baseline["base_qss"] + qss)

    logger.debug(
        "Applied accessibility: high_contrast=%s text_scale=%s focus_assist=%s",
        high_contrast, text_scale, focus_assist,
    )
