from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("schema-linker")
except PackageNotFoundError:
    # Keep this fallback aligned with pyproject.toml for source-tree execution.
    __version__ = "0.0.1"

from schema_linker.core import link_schema
from schema_linker.models import SchemaLinkOptions, SchemaLinkProgress

__all__ = [
    "SchemaLinkOptions",
    "SchemaLinkProgress",
    "__version__",
    "link_schema",
]
