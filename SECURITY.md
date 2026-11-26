# Security Policy

## Supported Versions

Security fixes are issued for the **latest minor release only**. Because
ToolsConnector is pre-1.0, the public API may change between minor versions;
backporting security fixes to older pre-1.0 lines is not practical. After
the 1.0 release, this policy will widen to cover at least the current major
and the previous major.

| Version | Supported |
|---------|-----------|
| 0.4.x   | Yes       |
| ≤ 0.3.x | No — please upgrade |

## Reporting a Vulnerability

If you discover a security vulnerability in ToolsConnector, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Preferred: use GitHub's **[Private Vulnerability Reporting](https://github.com/sachinshelke/ToolsConnector/security/advisories/new)**
(creates a private advisory and starts the coordinated-disclosure workflow).

Or email: **sachin.worldnet@gmail.com** with subject line starting `[SECURITY]`.

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 5 business days
- **Patch for critical issues:** Within 14 days
- **CVE assignment:** For any auth/credential vulnerability

## Security Design Principles

ToolsConnector follows these security principles:

1. **BYOK (Bring Your Own Key):** We never store, manage, or transmit credentials on our infrastructure. Developers own their API keys and choose how to store them.

2. **KeyStore abstraction:** Credentials are stored via a pluggable KeyStore interface. We provide InMemoryKeyStore (dev), EnvironmentKeyStore (CI), and LocalFileKeyStore (always encrypted; needs the `local-keystore` extra). Users can implement their own (Vault, AWS Secrets Manager, etc.).

3. **No credential logging:** Credentials are never written to logs, error messages, or telemetry. The structured logging system explicitly excludes auth headers.

4. **Input validation:** All tool call arguments are validated against JSON Schema before being sent to upstream APIs.

5. **Circuit breaker isolation:** A compromised or failing connector cannot affect other connectors in the same ToolKit.

6. **Dependency minimalism:** Core depends only on pydantic, httpx, and docstring-parser. Fewer dependencies = smaller attack surface.

7. **Tokens stay on the service's host:** actions that accept a next-page URL refuse any URL on another origin.

8. **No request without a credential:** a connector that declares a credential never sends a request without one.

## Known Security Considerations

- **REST serve layer** (`serve/rest.py`): Does not include authentication. If you expose it publicly, add your own auth middleware.
- **Services on your own host** (Jira, Confluence, Salesforce, Supabase, MongoDB, Redis): the built-in address is a placeholder. Subclass the connector with your address; see [Services on your own host](docs/guides/credentials.md#services-on-your-own-host).
- **Webhook connector**: sends its configured credential to whatever URL it is given.
- **MCP server over HTTP**: every session uses the credentials the server was started with, and there is no built-in authentication.
- **MCP server** (`serve/mcp.py`): Follows MCP security model — the client (Claude Desktop, Cursor) manages user consent for tool invocation.
- **Connector credentials in environment variables**: Ensure proper access controls on your environment. Consider using a KeyStore backend with encryption for production.
