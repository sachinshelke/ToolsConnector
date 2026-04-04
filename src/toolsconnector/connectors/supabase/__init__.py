"""Supabase connector -- PostgREST-based table operations and RPC."""

from __future__ import annotations

from .connector import Supabase
from .types import SupabaseRecord, SupabaseRPCResult, SupabaseTable

__all__ = [
    "Supabase",
    "SupabaseRecord",
    "SupabaseRPCResult",
    "SupabaseTable",
]
