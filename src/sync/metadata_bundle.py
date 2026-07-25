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


def _load_records(bundle_path):
    with zipfile.ZipFile(bundle_path) as zf:
        return json.loads(zf.read("elements.json").decode("utf-8"))


def _extract_preview(bundle_path, arc, previews_dir):
    if not arc or not previews_dir:
        return None
    try:
        with zipfile.ZipFile(bundle_path) as zf:
            data = zf.read(arc)
        dest = os.path.join(previews_dir, os.path.basename(arc))
        if not os.path.isdir(previews_dir):
            os.makedirs(previews_dir)
        with open(dest, "wb") as fh:
            fh.write(data)
        return dest
    except (OSError, KeyError):
        logger.exception("failed to extract preview %s", arc)
        return None


def import_bundle(db, bundle_path, target_list_id, conflict="timestamp", previews_dir=None):
    """Merge a bundle into target_list_id. Match by name; newest updated_at wins."""
    records = _load_records(bundle_path)
    existing = {e["name"]: e for e in db.get_elements_by_list(target_list_id,
                                                              include_deprecated=True)}
    summary = {"added": 0, "updated": 0, "skipped": 0}

    for rec in records:
        name = rec.get("name")
        preview_dest = _extract_preview(bundle_path, rec.get("preview_file"), previews_dir)
        payload = {k: rec.get(k) for k in
                   ("type", "format", "frame_range", "comment", "tags", "is_deprecated")}
        if preview_dest:
            payload["preview_path"] = preview_dest

        current = existing.get(name)
        if current is None:
            with db.get_connection() as conn:
                cols = ["list_fk", "name"] + list(payload.keys()) + ["updated_at"]
                vals = [target_list_id, name] + list(payload.values()) + [rec.get("updated_at")]
                placeholders = ", ".join("?" for _ in cols)
                conn.execute("INSERT INTO elements ({}) VALUES ({})".format(
                    ", ".join(cols), placeholders), vals)
                conn.commit()
            summary["added"] += 1
            continue

        incoming = rec.get("updated_at") or ""
        local = current.get("updated_at") or ""
        if conflict == "timestamp" and incoming > local:
            # update in place; preserve updated_at from the bundle
            payload_with_ts = dict(payload)
            payload_with_ts["updated_at"] = incoming
            with db.get_connection() as conn:
                set_clause = ", ".join("{} = ?".format(k) for k in payload_with_ts)
                conn.execute("UPDATE elements SET {} WHERE element_id = ?".format(set_clause),
                             list(payload_with_ts.values()) + [current["element_id"]])
                conn.commit()
            summary["updated"] += 1
        else:
            summary["skipped"] += 1

    if hasattr(db, "log_activity"):
        db.log_activity("system", "import", "bundle", target_list_id,
                        "added={added} updated={updated} skipped={skipped}".format(**summary))
    return summary
