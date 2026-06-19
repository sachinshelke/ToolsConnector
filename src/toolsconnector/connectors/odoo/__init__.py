"""Odoo (formerly OpenERP) connector -- full ORM access over JSON-RPC."""

from .connector import Odoo, OdooCredentials, parse_credentials
from .types import OdooVersion

__all__ = ["Odoo", "OdooCredentials", "OdooVersion", "parse_credentials"]
