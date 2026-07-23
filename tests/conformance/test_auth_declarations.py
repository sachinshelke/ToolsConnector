"""Every connector must declare how it is authenticated.

Platforms render "connect your tools" forms from ``get_spec().auth`` rather
than from prose, so an undeclared or drifting declaration is a real defect:
the form would ask for the wrong thing.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from toolsconnector.serve._discovery import _KNOWN_CONNECTORS
from toolsconnector.spec.auth import AuthType

CONNECTORS = sorted(_KNOWN_CONNECTORS.items())


def _load(path: str) -> type:
    module_path, class_name = path.split(":")
    return getattr(importlib.import_module(module_path), class_name)


@pytest.mark.parametrize(("name", "path"), CONNECTORS, ids=[n for n, _ in CONNECTORS])
def test_connector_declares_auth(name: str, path: str) -> None:
    auth = _load(path).get_spec().auth
    assert auth.supported, f"{name} declares no auth provider"
    assert isinstance(auth.default, AuthType), f"{name} has no default auth type"

    extra = auth.supported[0].extra
    fmt = extra.get("credential_format")
    assert fmt in {"string", "delimited", "json", "none"}, f"{name}: bad format {fmt!r}"

    fields = extra.get("fields")
    assert isinstance(fields, list), f"{name}: fields must be a list"
    if fmt == "none":
        assert fields == [], f"{name}: 'none' format must declare no fields"
        assert "env_var" not in extra, f"{name}: credential-free connector needs no env var"
    else:
        assert fields, f"{name}: {fmt} format must declare at least one field"
        assert extra["env_var"] == f"TC_{name.upper()}_CREDENTIALS"
    for field in fields:
        assert set(field) >= {"name", "label", "required", "secret"}, f"{name}: {field}"

    if fmt == "delimited":
        assert extra.get("separator"), f"{name}: delimited format needs a separator"
        assert extra.get("order") == [f["name"] for f in fields], f"{name}: bad order"


@pytest.mark.parametrize(("name", "path"), CONNECTORS, ids=[n for n, _ in CONNECTORS])
def test_declared_header_matches_implementation(name: str, path: str) -> None:
    """The declared header/prefix must actually appear in the connector."""
    cls = _load(path)
    provider = cls.get_spec().auth.supported[0]
    if provider.api_key is None:
        return
    source = inspect.getsource(cls)
    header = provider.api_key.param_name
    prefix = provider.api_key.prefix
    if header:
        assert header in source, f"{name} declares header {header!r} but never sends it"
    # "Basic" is assembled via base64 helpers, so only check literal prefixes.
    if prefix and prefix != "Basic":
        assert prefix in source, f"{name} declares prefix {prefix!r} but never sends it"
