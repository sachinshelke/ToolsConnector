# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in ToolsConnector, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email: **security@toolsconnector.dev**

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

2. **KeyStore abstraction:** Credentials are stored via a pluggable KeyStore interface. We provide InMemoryKeyStore (dev), EnvironmentKeyStore (CI), and LocalFileKeyStore (encrypted). Users can implement their own (Vault, AWS Secrets Manager, etc.).

3. **No credential logging:** Credentials are never written to logs, error messages, or telemetry. The structured logging system explicitly excludes auth headers.

4. **Input validation:** All tool call arguments are validated against JSON Schema before being sent to upstream APIs.

5. **Circuit breaker isolation:** A compromised or failing connector cannot affect other connectors in the same ToolKit.

6. **Dependency minimalism:** Core depends only on pydantic, httpx, and docstring-parser. Fewer dependencies = smaller attack surface.

## Known Security Considerations

- **REST serve layer** (`serve/rest.py`): Does not include authentication. If you expose it publicly, add your own auth middleware.
- **MCP server** (`serve/mcp.py`): Follows MCP security model — the client (Claude Desktop, Cursor) manages user consent for tool invocation.
- **Connector credentials in environment variables**: Ensure proper access controls on your environment. Consider using a KeyStore backend with encryption for production.
