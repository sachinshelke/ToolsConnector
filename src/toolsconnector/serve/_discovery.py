"""Connector registry with lazy loading.

Maps connector names to their module paths. Imports happen lazily
to avoid loading all 50 connectors (and their dependencies) at startup.
"""

from __future__ import annotations

import importlib
from typing import Any

# Map connector name -> "module.path:ClassName"
_KNOWN_CONNECTORS: dict[str, str] = {
    "gmail": "toolsconnector.connectors.gmail:Gmail",
    "gdrive": "toolsconnector.connectors.gdrive:GoogleDrive",
    "gcalendar": "toolsconnector.connectors.gcalendar:GoogleCalendar",
    "slack": "toolsconnector.connectors.slack:Slack",
    "discord": "toolsconnector.connectors.discord:Discord",
    "github": "toolsconnector.connectors.github:GitHub",
    "gitlab": "toolsconnector.connectors.gitlab:GitLab",
    "notion": "toolsconnector.connectors.notion:Notion",
    "jira": "toolsconnector.connectors.jira:Jira",
    "linear": "toolsconnector.connectors.linear:Linear",
    "outlook": "toolsconnector.connectors.outlook:Outlook",
    "teams": "toolsconnector.connectors.teams:Teams",
    "confluence": "toolsconnector.connectors.confluence:Confluence",
    "asana": "toolsconnector.connectors.asana:Asana",
    "hubspot": "toolsconnector.connectors.hubspot:HubSpot",
    "salesforce": "toolsconnector.connectors.salesforce:Salesforce",
    "stripe": "toolsconnector.connectors.stripe:Stripe",
    "twilio": "toolsconnector.connectors.twilio:Twilio",
    "sendgrid": "toolsconnector.connectors.sendgrid:SendGrid",
    "s3": "toolsconnector.connectors.s3:S3",
    "supabase": "toolsconnector.connectors.supabase:Supabase",
    "mongodb": "toolsconnector.connectors.mongodb:MongoDB",
    "airtable": "toolsconnector.connectors.airtable:Airtable",
    "firestore": "toolsconnector.connectors.firestore:Firestore",
    "redis": "toolsconnector.connectors.redis_connector:Redis",
    "datadog": "toolsconnector.connectors.datadog:Datadog",
    "pagerduty": "toolsconnector.connectors.pagerduty:PagerDuty",
    "vercel": "toolsconnector.connectors.vercel:Vercel",
    "cloudflare": "toolsconnector.connectors.cloudflare:Cloudflare",
    "dockerhub": "toolsconnector.connectors.dockerhub:DockerHub",
    "openai": "toolsconnector.connectors.openai_connector:OpenAI",
    "anthropic": "toolsconnector.connectors.anthropic_connector:Anthropic",
    "pinecone": "toolsconnector.connectors.pinecone:Pinecone",
    "mixpanel": "toolsconnector.connectors.mixpanel:Mixpanel",
    "segment": "toolsconnector.connectors.segment:Segment",
    "shopify": "toolsconnector.connectors.shopify:Shopify",
    "trello": "toolsconnector.connectors.trello:Trello",
    "figma": "toolsconnector.connectors.figma:Figma",
    "zendesk": "toolsconnector.connectors.zendesk:Zendesk",
    "mailchimp": "toolsconnector.connectors.mailchimp:Mailchimp",
    "sqs": "toolsconnector.connectors.sqs:SQS",
    "rabbitmq": "toolsconnector.connectors.rabbitmq:RabbitMQ",
    "okta": "toolsconnector.connectors.okta:Okta",
    "auth0": "toolsconnector.connectors.auth0:Auth0",
    "telegram": "toolsconnector.connectors.telegram:Telegram",
    "freshdesk": "toolsconnector.connectors.freshdesk:Freshdesk",
    "calendly": "toolsconnector.connectors.calendly:Calendly",
    "intercom": "toolsconnector.connectors.intercom:Intercom",
    "plaid": "toolsconnector.connectors.plaid:Plaid",
    "webhook": "toolsconnector.connectors.webhook:Webhook",
}

# Install hints for when imports fail
_INSTALL_HINTS: dict[str, str] = {
    name: f"toolsconnector[{name}]" for name in _KNOWN_CONNECTORS
}

from toolsconnector.errors import ConnectorNotConfiguredError, ConnectorInitError


def list_connectors() -> list[str]:
    """Return sorted list of all available connector names.

    Returns:
        Alphabetically sorted list of registered connector names.
    """
    return sorted(_KNOWN_CONNECTORS.keys())


def get_connector_class(name: str) -> type:
    """Lazily import and return a connector class by name.

    Args:
        name: Connector name (e.g., ``"gmail"``).

    Returns:
        The connector class (a ``BaseConnector`` subclass).

    Raises:
        ConnectorNotConfiguredError: If the name is not in the registry.
        ConnectorInitError: If the import fails (missing dependencies).
    """
    if name not in _KNOWN_CONNECTORS:
        available = ", ".join(sorted(_KNOWN_CONNECTORS.keys())[:10])
        raise ConnectorNotConfiguredError(
            f"Unknown connector '{name}'.",
            connector=name,
            suggestion=(
                f"Available connectors: {available}... "
                f"Use list_connectors() for full list."
            ),
        )

    module_path, class_name = _KNOWN_CONNECTORS[name].rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except ImportError as e:
        pkg = _INSTALL_HINTS.get(name, f"toolsconnector[{name}]")
        raise ConnectorInitError(
            f"Connector '{name}' requires additional dependencies.",
            connector=name,
            suggestion=f"Install with: pip install {pkg}",
            details={"import_error": str(e)},
        ) from e
    except AttributeError as e:
        raise ConnectorInitError(
            f"Connector class '{class_name}' not found in '{module_path}'.",
            connector=name,
            details={"attribute_error": str(e)},
        ) from e


def resolve_connectors(connectors: list[Any]) -> list[type]:
    """Accept a mix of connector classes and name strings, return classes.

    This is the primary entry point used by ``ToolKit`` to normalize
    the ``connectors`` argument into a uniform list of classes.

    Args:
        connectors: List of ``BaseConnector`` subclasses or connector
            name strings (e.g., ``["gmail", "slack", MyCustomConnector]``).

    Returns:
        List of connector classes ready for instantiation.
    """
    result: list[type] = []
    for c in connectors:
        if isinstance(c, str):
            result.append(get_connector_class(c))
        else:
            result.append(c)
    return result
