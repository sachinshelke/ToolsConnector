"""Pydantic models for Twilio connector types.

All response models use ``frozen=True`` to enforce immutability.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TwilioMessage(BaseModel):
    """A Twilio SMS/MMS message."""

    model_config = ConfigDict(frozen=True)

    sid: str
    account_sid: Optional[str] = None
    to: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    body: Optional[str] = None
    status: Optional[str] = None
    direction: Optional[str] = None
    price: Optional[str] = None
    price_unit: Optional[str] = None
    num_segments: Optional[str] = None
    num_media: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    uri: Optional[str] = None
    date_created: Optional[str] = None
    date_updated: Optional[str] = None
    date_sent: Optional[str] = None


class TwilioCall(BaseModel):
    """A Twilio voice call."""

    model_config = ConfigDict(frozen=True)

    sid: str
    account_sid: Optional[str] = None
    to: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    status: Optional[str] = None
    direction: Optional[str] = None
    duration: Optional[str] = None
    price: Optional[str] = None
    price_unit: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    phone_number_sid: Optional[str] = None
    uri: Optional[str] = None
    date_created: Optional[str] = None
    date_updated: Optional[str] = None


class PhoneNumber(BaseModel):
    """A Twilio incoming phone number."""

    model_config = ConfigDict(frozen=True)

    sid: str
    account_sid: Optional[str] = None
    phone_number: Optional[str] = None
    friendly_name: Optional[str] = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    status: Optional[str] = None
    date_created: Optional[str] = None
    date_updated: Optional[str] = None
    uri: Optional[str] = None


class TwilioAccount(BaseModel):
    """A Twilio account."""

    model_config = ConfigDict(frozen=True)

    sid: str
    friendly_name: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    owner_account_sid: Optional[str] = None
    date_created: Optional[str] = None
    date_updated: Optional[str] = None
    uri: Optional[str] = None


class TwilioRecording(BaseModel):
    """A Twilio call recording."""

    model_config = ConfigDict(frozen=True)

    sid: str
    account_sid: Optional[str] = None
    call_sid: Optional[str] = None
    duration: Optional[str] = None
    channels: Optional[int] = None
    status: Optional[str] = None
    price: Optional[str] = None
    price_unit: Optional[str] = None
    source: Optional[str] = None
    uri: Optional[str] = None
    date_created: Optional[str] = None
    date_updated: Optional[str] = None


class TwilioUsageRecord(BaseModel):
    """A Twilio usage record."""

    model_config = ConfigDict(frozen=True)

    category: str
    description: Optional[str] = None
    count: Optional[str] = None
    count_unit: Optional[str] = None
    usage: Optional[str] = None
    usage_unit: Optional[str] = None
    price: Optional[str] = None
    price_unit: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    uri: Optional[str] = None
