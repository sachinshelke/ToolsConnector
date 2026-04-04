"""Twilio API response parsers.

Helper functions to parse raw JSON dicts from the Twilio API
into typed Pydantic models.
"""

from __future__ import annotations

from typing import Any

from .types import PhoneNumber, TwilioCall, TwilioMessage


def parse_message(data: dict[str, Any]) -> TwilioMessage:
    """Parse a TwilioMessage from API JSON.

    Args:
        data: Raw JSON dict from the Twilio API.

    Returns:
        A TwilioMessage instance.
    """
    return TwilioMessage(
        sid=data["sid"],
        account_sid=data.get("account_sid"),
        to=data.get("to"),
        from_=data.get("from"),
        body=data.get("body"),
        status=data.get("status"),
        direction=data.get("direction"),
        price=data.get("price"),
        price_unit=data.get("price_unit"),
        num_segments=data.get("num_segments"),
        num_media=data.get("num_media"),
        error_code=data.get("error_code"),
        error_message=data.get("error_message"),
        uri=data.get("uri"),
        date_created=data.get("date_created"),
        date_updated=data.get("date_updated"),
        date_sent=data.get("date_sent"),
    )


def parse_call(data: dict[str, Any]) -> TwilioCall:
    """Parse a TwilioCall from API JSON.

    Args:
        data: Raw JSON dict from the Twilio API.

    Returns:
        A TwilioCall instance.
    """
    return TwilioCall(
        sid=data["sid"],
        account_sid=data.get("account_sid"),
        to=data.get("to"),
        from_=data.get("from"),
        status=data.get("status"),
        direction=data.get("direction"),
        duration=data.get("duration"),
        price=data.get("price"),
        price_unit=data.get("price_unit"),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
        phone_number_sid=data.get("phone_number_sid"),
        uri=data.get("uri"),
        date_created=data.get("date_created"),
        date_updated=data.get("date_updated"),
    )


def parse_phone_number(data: dict[str, Any]) -> PhoneNumber:
    """Parse a PhoneNumber from API JSON.

    Args:
        data: Raw JSON dict from the Twilio API.

    Returns:
        A PhoneNumber instance.
    """
    return PhoneNumber(
        sid=data["sid"],
        account_sid=data.get("account_sid"),
        phone_number=data.get("phone_number"),
        friendly_name=data.get("friendly_name"),
        capabilities=data.get("capabilities") or {},
        status=data.get("status"),
        date_created=data.get("date_created"),
        date_updated=data.get("date_updated"),
        uri=data.get("uri"),
    )
