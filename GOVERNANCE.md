# Governance

ToolsConnector is an open source project licensed under Apache 2.0.
This document describes how the project is governed.

## Roles

### Maintainers

Maintainers have full commit access and are responsible for:

- Reviewing and merging pull requests
- Triaging issues
- Making release decisions
- Enforcing the Code of Conduct
- Architectural decisions (via RFC process)

**Current maintainers:**
- Sachin (Founder, BDFL)

### Committers

Committers have write access to the repository and can merge PRs
after maintainer approval. Committers are nominated by maintainers
based on sustained, high-quality contributions.

### Contributors

Anyone who submits a pull request, issue, or documentation improvement.
All contributors are recognized in the CONTRIBUTORS file.

## Decision Making

### Day-to-day decisions

Made by maintainers through GitHub issues and pull requests.
Simple majority among active maintainers for non-controversial changes.

### Architectural decisions

Significant changes to the core architecture require an RFC:

1. Open a GitHub Discussion with `[RFC]` prefix
2. Describe the problem, proposed solution, and alternatives
3. Allow 2-week comment period
4. Maintainer approval required
5. Document the decision in `docs/ARCHITECTURE_FAQ.md`

### What requires an RFC

- Changes to `spec/` module (affects all language SDKs)
- New authentication providers in `runtime/auth/`
- Changes to the ToolKit public API
- New protocol adapters
- Breaking changes to any public interface

### What does NOT require an RFC

- New connectors (standard PR process)
- Bug fixes
- Documentation improvements
- Test additions
- Internal refactoring that doesn't change public API

## Releases

- **Version format:** Semantic Versioning (MAJOR.MINOR.PATCH)
- **Release cadence:** Monthly for minor versions, as-needed for patches
- **Release process:** Maintainer creates a GitHub Release with changelog
- **Breaking changes:** Only in major versions, with deprecation notices
  in the prior minor version

## Evolution

As the project grows:

- **At 10+ regular contributors:** Add a second maintainer
- **At 50+ contributors:** Form a steering committee (3-5 people)
- **At 3+ major company adopters:** Evaluate foundation governance
  (CNCF, Linux Foundation, or independent foundation)

## Code of Conduct

All participants must follow our [Code of Conduct](CODE_OF_CONDUCT.md).
