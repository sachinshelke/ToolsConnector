"""Multi-tenant ToolKit for SaaS platforms.

ToolKitFactory creates isolated ToolKit instances per user/tenant.
Each tenant gets their own credentials, connector instances, and
circuit breakers -- no cross-tenant data leakage.

This pattern is designed for platforms like AgentStore where
many users share the same connector configuration but bring
their own API tokens.
"""

from toolsconnector.serve import ToolKitFactory

# Create a factory with shared configuration.
# The factory does NOT hold credentials -- those are per-tenant.
factory = ToolKitFactory(
    connectors=["gmail", "slack"],
    exclude_dangerous=True,
    timeout_budget=15.0,
)

# Create per-user toolkits.
# Each call to for_tenant() returns an isolated ToolKit with its
# own connector instances and circuit breakers.
user_a_kit = factory.for_tenant(
    tenant_id="user-alice",
    credentials={
        "gmail": "alice-gmail-token",
        "slack": "alice-slack-token",
    },
)

user_b_kit = factory.for_tenant(
    tenant_id="user-bob",
    credentials={
        "gmail": "bob-gmail-token",
        "slack": "bob-slack-token",
    },
)

# Inspect what was created
print(f"Active tenants: {factory.active_tenants}")
print(f"Alice's tools: {len(user_a_kit.list_tools())}")
print(f"Bob's tools:   {len(user_b_kit.list_tools())}")

# Each user's actions are fully isolated.
# Alice's Gmail token is never used for Bob's requests.
# result = user_a_kit.execute("gmail_list_emails", {"query": "is:unread"})
