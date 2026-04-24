"""Shared helpers for connector implementations.

Cross-connector utilities that are too small for their own modules and
too connector-specific to live in ``runtime/``. Add things here only
when at least 2 connectors would benefit; otherwise keep them inline
in the connector that needs them.
"""

from .http_errors import raise_typed_for_status

__all__ = ["raise_typed_for_status"]
