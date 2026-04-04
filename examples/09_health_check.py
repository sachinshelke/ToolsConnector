"""Check connector health and export specs.

Useful for CI/CD pipelines and monitoring dashboards.
The health checker validates specs without making real API calls
(unless you supply credentials for live checks).
"""

from toolsconnector.codegen import extract_spec, generate_openapi
from toolsconnector.health import (
    HealthChecker,
    generate_health_report_markdown,
)

# -- Health check --
# HealthChecker validates that every connector:
#   1. Can be imported
#   2. Produces a valid spec (name, actions, schemas)
#   3. Can be instantiated (if credentials are provided)
checker = HealthChecker()
report = checker.check_all_sync()

# Print a Markdown-formatted report
print(generate_health_report_markdown(report))
print(f"\nHealthy: {report.healthy}/{report.total}")

# -- Spec extraction --
# extract_spec() returns a single connector's spec as a dict.
# This is the same data used by to_openai_tools() and to_anthropic_tools().
gmail_spec = extract_spec("gmail")
print(f"\nGmail: {len(gmail_spec['actions'])} actions")

# -- OpenAPI generation --
# generate_openapi() produces a standard OpenAPI 3.1 spec for a set
# of connectors. Useful for documentation or REST API tooling.
openapi = generate_openapi(["gmail", "slack", "github"])
print(f"OpenAPI paths: {len(openapi['paths'])}")
