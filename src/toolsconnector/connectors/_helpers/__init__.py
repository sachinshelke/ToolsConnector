"""Shared helpers for connector implementations.

Cross-connector utilities that are too small for their own modules and
too connector-specific to live in ``runtime/``. Add things here only
when at least 2 connectors would benefit; otherwise keep them inline
in the connector that needs them.
"""

from .http_errors import (
    _parse_retry_after as parse_retry_after,
)
from .http_errors import (
    _redact_credentials as redact_credentials,
)
from .http_errors import (
    raise_typed_for_status,
)
from .sanitize import (
    coerce_optional_int,
    dict_list,
    require_dict,
    safe_int,
    safe_validate,
    scrub_secret,
    validate_list,
)

__all__ = [
    "raise_typed_for_status",
    "redact_credentials",
    "parse_retry_after",
    "safe_int",
    "coerce_optional_int",
    "dict_list",
    "safe_validate",
    "validate_list",
    "require_dict",
    "scrub_secret",
]
