"""Smart tool selection for large connector deployments.

When 50 connectors with 395 tools are loaded, sending all of them
to the LLM wastes context tokens. SmartToolSelector filters tools
based on a natural language query using keyword matching.

For deployments with <20 tools, filtering is unnecessary.
For 50+ tools, this saves significant tokens.
"""

from __future__ import annotations

import re
from typing import Any, Optional


# Keyword mappings for common intents
_INTENT_KEYWORDS: dict[str, list[str]] = {
    "email": ["gmail", "outlook", "sendgrid", "mailchimp"],
    "mail": ["gmail", "outlook", "sendgrid"],
    "message": ["slack", "discord", "teams", "telegram", "twilio"],
    "chat": ["slack", "discord", "teams", "telegram"],
    "sms": ["twilio"],
    "code": ["github", "gitlab"],
    "repository": ["github", "gitlab"],
    "pull request": ["github", "gitlab"],
    "issue": ["github", "gitlab", "jira", "linear"],
    "project": ["jira", "asana", "linear", "trello", "notion"],
    "task": ["jira", "asana", "linear", "trello"],
    "ticket": ["jira", "zendesk", "freshdesk"],
    "customer": ["hubspot", "salesforce", "intercom"],
    "contact": ["hubspot", "salesforce"],
    "deal": ["hubspot", "salesforce"],
    "crm": ["hubspot", "salesforce"],
    "file": ["gdrive", "s3", "dropbox"],
    "storage": ["s3", "gdrive"],
    "document": ["notion", "confluence", "gdrive"],
    "wiki": ["notion", "confluence"],
    "page": ["notion", "confluence"],
    "calendar": ["gcalendar", "calendly"],
    "event": ["gcalendar", "calendly"],
    "meeting": ["gcalendar", "calendly", "teams"],
    "database": ["supabase", "mongodb", "airtable", "firestore"],
    "record": ["airtable", "supabase", "salesforce"],
    "query": ["supabase", "mongodb", "salesforce"],
    "monitor": ["datadog", "pagerduty"],
    "alert": ["datadog", "pagerduty"],
    "incident": ["pagerduty"],
    "deploy": ["vercel", "cloudflare"],
    "dns": ["cloudflare"],
    "domain": ["cloudflare", "vercel"],
    "container": ["dockerhub"],
    "docker": ["dockerhub"],
    "ai": ["openai", "anthropic", "pinecone"],
    "llm": ["openai", "anthropic"],
    "embedding": ["openai", "pinecone"],
    "vector": ["pinecone"],
    "analytics": ["mixpanel", "segment"],
    "track": ["mixpanel", "segment"],
    "payment": ["stripe", "plaid"],
    "invoice": ["stripe"],
    "bank": ["plaid"],
    "queue": ["sqs", "rabbitmq"],
    "user": ["okta", "auth0"],
    "identity": ["okta", "auth0"],
    "auth": ["okta", "auth0"],
    "webhook": ["webhook"],
    "design": ["figma"],
    "shop": ["shopify"],
    "product": ["shopify"],
    "order": ["shopify"],
}


class SmartToolSelector:
    """Selects relevant tools based on a natural language query.

    Uses keyword matching to identify which connectors are relevant
    to a user's request, then filters the ToolKit's tool list.

    Usage::

        from toolsconnector.serve import ToolKit
        from toolsconnector_mcp import SmartToolSelector

        kit = ToolKit(["gmail", "slack", "github", "jira", "notion"])
        selector = SmartToolSelector(kit)

        # Get only relevant tools for a query
        tools = selector.select("send an email to the team about the PR")
        # Returns: gmail + slack tools (email + message intent)
    """

    def __init__(
        self,
        toolkit: Any,
        *,
        max_tools: int = 30,
        always_include: Optional[list[str]] = None,
    ) -> None:
        """Initialize the selector.

        Args:
            toolkit: A ToolKit instance.
            max_tools: Maximum tools to return.
            always_include: Connector names to always include.
        """
        self._toolkit = toolkit
        self._max_tools = max_tools
        self._always_include = set(always_include or [])
        self._all_tools = toolkit.list_tools()

    def select(self, query: str) -> list[dict[str, Any]]:
        """Select relevant tools for a natural language query.

        Args:
            query: The user's request in natural language.

        Returns:
            Filtered list of tool dicts, most relevant first.
        """
        query_lower = query.lower()
        connector_scores: dict[str, float] = {}

        # Score connectors by keyword matches
        for keyword, connectors in _INTENT_KEYWORDS.items():
            if keyword in query_lower:
                for conn in connectors:
                    connector_scores[conn] = (
                        connector_scores.get(conn, 0) + 1.0
                    )

        # Always include specified connectors
        for conn in self._always_include:
            connector_scores[conn] = (
                connector_scores.get(conn, 0) + 10.0
            )

        # If no matches, return all tools (no filtering)
        if not connector_scores:
            return self._all_tools[: self._max_tools]

        # Sort connectors by score (highest first)
        ranked = sorted(
            connector_scores.keys(),
            key=lambda c: connector_scores[c],
            reverse=True,
        )

        # Collect tools from ranked connectors
        result: list[dict[str, Any]] = []
        for conn in ranked:
            for tool in self._all_tools:
                if tool["connector"] == conn and len(result) < self._max_tools:
                    result.append(tool)

        return result

    def select_connectors(self, query: str) -> list[str]:
        """Select relevant connector names for a query.

        Args:
            query: The user's request.

        Returns:
            List of connector names, most relevant first.
        """
        tools = self.select(query)
        seen: list[str] = []
        for t in tools:
            if t["connector"] not in seen:
                seen.append(t["connector"])
        return seen
