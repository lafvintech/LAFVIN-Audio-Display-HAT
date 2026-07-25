"""Application manifests and lifecycle management."""

from .manager import AppManager
from .manifest import AppManifest, ManifestError, load_manifest

__all__ = ["AppManager", "AppManifest", "ManifestError", "load_manifest"]

