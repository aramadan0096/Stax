# -*- coding: utf-8 -*-
"""Collaboration connector seam (EP8). EP8 ships only the local-bundle path;
Kitsu/Ftrack/Flow/DCC bridges are follow-on subclasses (see the EP8 design §10).
No third-party SDK is imported here."""

import logging

logger = logging.getLogger(__name__)


class CollaborationConnector(object):
    """Base class for external collaboration bridges."""
    key = "base"
    label = "Base Connector"

    def is_available(self):
        """True when this connector is configured/usable in the environment."""
        return False

    def capabilities(self):
        """Subset of {'push', 'pull', 'status', 'notes'}."""
        return set()

    def push(self, payload):
        raise NotImplementedError

    def pull(self):
        raise NotImplementedError


class LocalBundleConnector(CollaborationConnector):
    """The only concrete connector EP8 ships: wraps metadata_bundle export/import."""
    key = "local_bundle"
    label = "Local Bundle (.staxbundle)"

    def is_available(self):
        return True

    def capabilities(self):
        return {"push", "pull"}

    def push(self, payload):
        from sync.metadata_bundle import export_list_bundle
        return export_list_bundle(payload["db"], payload["list_id"], payload["out_path"],
                                  source_site=payload.get("source_site", ""))

    def pull(self, payload=None):
        from sync.metadata_bundle import import_bundle
        payload = payload or {}
        return import_bundle(payload["db"], payload["bundle_path"], payload["target_list_id"],
                             previews_dir=payload.get("previews_dir"))


_REGISTRY = []


def register_connector(cls):
    if cls not in _REGISTRY:
        _REGISTRY.append(cls)
    return cls


def get_connectors():
    return [cls() for cls in _REGISTRY]


register_connector(LocalBundleConnector)
