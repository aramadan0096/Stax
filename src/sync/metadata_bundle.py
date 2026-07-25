# -*- coding: utf-8 -*-
"""Portable metadata + preview bundle export/import (EP8, F041).
Stdlib only: json, zipfile, shutil, os, datetime. Network-free."""

import os
import json
import zipfile
import datetime
import logging

logger = logging.getLogger(__name__)

BUNDLE_VERSION = 1

# element columns that travel in the bundle
_FIELDS = ("name", "type", "format", "frame_range", "comment", "tags",
           "is_deprecated", "created_at", "updated_at")


def _iso_now():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def export_list_bundle(db, list_id, out_path, source_site="", include_previews=True):
    """Serialize a list's elements + metadata + previews into a .staxbundle zip."""
    lst = db.get_list_by_id(list_id)
    elements = db.get_elements_by_list(list_id, include_deprecated=True)

    records, preview_map = [], {}
    for el in elements:
        rec = {k: el.get(k) for k in _FIELDS}
        rec["preview_file"] = None
        preview = el.get("preview_path")
        if include_previews and preview and os.path.exists(preview):
            arc = "previews/{}_{}".format(el["element_id"], os.path.basename(preview))
            rec["preview_file"] = arc
            preview_map[arc] = preview
        records.append(rec)

    manifest = {
        "bundle_version": BUNDLE_VERSION,
        "source_site": source_site,
        "exported_at": _iso_now(),
        "scope": {"type": "list", "id": list_id,
                  "name": lst["name"] if lst else str(list_id)},
        "element_count": len(records),
    }

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("elements.json", json.dumps(records, indent=2))
        for arc, src in preview_map.items():
            try:
                zf.write(src, arc)
            except OSError:
                logger.exception("failed to add preview %s", src)
    if hasattr(db, "log_activity"):
        db.log_activity(source_site or "system", "export", "bundle", list_id,
                        "{} elements".format(len(records)))
    return out_path


def read_manifest(bundle_path):
    with zipfile.ZipFile(bundle_path) as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))
