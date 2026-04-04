"""Expose connectors as a REST API.

ToolKit can generate an ASGI app (Starlette) that serves your
connectors over HTTP. Useful for language-agnostic integrations
or when your AI agent runtime expects a REST backend.

Prerequisites:
    pip install toolsconnector[rest,gmail,slack]
    export TC_GMAIL_CREDENTIALS='your-token'
    export TC_SLACK_CREDENTIALS='your-token'

Then test with curl:
    curl http://localhost:8000/api/v1/connectors
    curl -X POST http://localhost:8000/api/v1/gmail/list_emails \
         -H "Content-Type: application/json" \
         -d '{"query": "is:unread", "limit": 5}'
"""

from toolsconnector.serve import ToolKit

# Create a ToolKit with safety filtering.
kit = ToolKit(
    connectors=["gmail", "slack"],
    exclude_dangerous=True,
)

# create_rest_app() returns a Starlette ASGI application.
# It exposes POST /{connector}/{action} endpoints for every tool.
app = kit.create_rest_app()

if __name__ == "__main__":
    import uvicorn

    print(f"Starting REST API with {len(kit.list_tools())} tools...")
    print("Docs: http://localhost:8000/api/v1/connectors")
    uvicorn.run(app, host="0.0.0.0", port=8000)
