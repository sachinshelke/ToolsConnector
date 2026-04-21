"""Connector registry with lazy loading.

Maps connector names to their module paths. Imports happen lazily
to avoid loading all 60 connectors (and their dependencies) at startup.
"""

from __future__ import annotations

import importlib
from typing import Any

# Map connector name -> "module.path:ClassName"
_KNOWN_CONNECTORS: dict[str, str] = {
    "acm": "toolsconnector.connectors.acm:ACM",
    "airtable": "toolsconnector.connectors.airtable:Airtable",
    "alb": "toolsconnector.connectors.alb:ALB",
    "anthropic": "toolsconnector.connectors.anthropic_connector:Anthropic",
    "asana": "toolsconnector.connectors.asana:Asana",
    "auth0": "toolsconnector.connectors.auth0:Auth0",
    "calendly": "toolsconnector.connectors.calendly:Calendly",
    "cloudflare": "toolsconnector.connectors.cloudflare:Cloudflare",
    "cloudfront": "toolsconnector.connectors.cloudfront:CloudFront",
    "cloudwatch": "toolsconnector.connectors.cloudwatch:CloudWatch",
    "confluence": "toolsconnector.connectors.confluence:Confluence",
    "datadog": "toolsconnector.connectors.datadog:Datadog",
    "discord": "toolsconnector.connectors.discord:Discord",
    "dockerhub": "toolsconnector.connectors.dockerhub:DockerHub",
    "ec2": "toolsconnector.connectors.ec2:EC2",
    "ecr": "toolsconnector.connectors.ecr:ECR",
    "ecs": "toolsconnector.connectors.ecs:ECS",
    "figma": "toolsconnector.connectors.figma:Figma",
    "firestore": "toolsconnector.connectors.firestore:Firestore",
    "freshdesk": "toolsconnector.connectors.freshdesk:Freshdesk",
    "gcalendar": "toolsconnector.connectors.gcalendar:GoogleCalendar",
    "gdocs": "toolsconnector.connectors.gdocs:GoogleDocs",
    "gdrive": "toolsconnector.connectors.gdrive:GoogleDrive",
    "github": "toolsconnector.connectors.github:GitHub",
    "gitlab": "toolsconnector.connectors.gitlab:GitLab",
    "gmail": "toolsconnector.connectors.gmail:Gmail",
    "gsheets": "toolsconnector.connectors.gsheets:GoogleSheets",
    "gtasks": "toolsconnector.connectors.gtasks:GoogleTasks",
    "hubspot": "toolsconnector.connectors.hubspot:HubSpot",
    "iam": "toolsconnector.connectors.iam:IAM",
    "intercom": "toolsconnector.connectors.intercom:Intercom",
    "jira": "toolsconnector.connectors.jira:Jira",
    "lambda_connector": "toolsconnector.connectors.lambda_connector:Lambda",
    "linear": "toolsconnector.connectors.linear:Linear",
    "linkedin": "toolsconnector.connectors.linkedin:LinkedIn",
    "mailchimp": "toolsconnector.connectors.mailchimp:Mailchimp",
    "medium": "toolsconnector.connectors.medium:Medium",
    "mixpanel": "toolsconnector.connectors.mixpanel:Mixpanel",
    "mongodb": "toolsconnector.connectors.mongodb:MongoDB",
    "notion": "toolsconnector.connectors.notion:Notion",
    "okta": "toolsconnector.connectors.okta:Okta",
    "openai": "toolsconnector.connectors.openai_connector:OpenAI",
    "outlook": "toolsconnector.connectors.outlook:Outlook",
    "pagerduty": "toolsconnector.connectors.pagerduty:PagerDuty",
    "pinecone": "toolsconnector.connectors.pinecone:Pinecone",
    "plaid": "toolsconnector.connectors.plaid:Plaid",
    "rabbitmq": "toolsconnector.connectors.rabbitmq:RabbitMQ",
    "rds": "toolsconnector.connectors.rds:RDS",
    "redis": "toolsconnector.connectors.redis_connector:Redis",
    "route53": "toolsconnector.connectors.route53:Route53",
    "s3": "toolsconnector.connectors.s3:S3",
    "salesforce": "toolsconnector.connectors.salesforce:Salesforce",
    "secrets_manager": "toolsconnector.connectors.secrets_manager:SecretsManager",
    "segment": "toolsconnector.connectors.segment:Segment",
    "sendgrid": "toolsconnector.connectors.sendgrid:SendGrid",
    "shopify": "toolsconnector.connectors.shopify:Shopify",
    "slack": "toolsconnector.connectors.slack:Slack",
    "sqs": "toolsconnector.connectors.sqs:SQS",
    "stripe": "toolsconnector.connectors.stripe:Stripe",
    "supabase": "toolsconnector.connectors.supabase:Supabase",
    "teams": "toolsconnector.connectors.teams:Teams",
    "telegram": "toolsconnector.connectors.telegram:Telegram",
    "trello": "toolsconnector.connectors.trello:Trello",
    "twilio": "toolsconnector.connectors.twilio:Twilio",
    "vercel": "toolsconnector.connectors.vercel:Vercel",
    "webhook": "toolsconnector.connectors.webhook:Webhook",
    "x": "toolsconnector.connectors.x:X",
    "zendesk": "toolsconnector.connectors.zendesk:Zendesk",
}

# Install hints for when imports fail
_INSTALL_HINTS: dict[str, str] = {name: f"toolsconnector[{name}]" for name in _KNOWN_CONNECTORS}

from toolsconnector.errors import ConnectorInitError, ConnectorNotConfiguredError


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
                f"Available connectors: {available}... Use list_connectors() for full list."
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
