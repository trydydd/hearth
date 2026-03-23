# CafeBox Architecture Guide

This document is the source of truth for architectural and code-organization decisions.

## Scope

Use this guide for decisions about:

- Ansible role boundaries and dependency ownership
- Service packaging and portability
- Security and runtime assumptions that affect implementation structure
- Tradeoffs that should remain stable as the project grows

Keep UX-specific guidance in `STYLEGUIDE.md` and testing process details in `TESTING.md`.

## Core Principles

- Keep role logic explicit and readable.
- Optimize for portability and maintainability over clever abstractions.
- Prefer conventions that reduce hidden coupling.
- Make security boundaries clear in code and provisioning.

## Ansible Role Boundaries

- Service roles may assume baseline system packages are installed by the common role.
- Service roles should not depend on custom variables from other roles to derive service-local application paths.
- Keep service-local path decisions explicit inside each service role.
- Prefer simple, self-contained role logic over cross-role variable conventions for one-off layout rules.

## Dependency Ownership

Use this rule of thumb:

- **Common role**: host-level prerequisites needed broadly across services.
- **Service role**: service-specific runtime behavior, filesystem layout, and service dependencies.

Promote a dependency to common only when it is a genuine platform concern, not a one-role convenience.

## Decision Records

For major architectural changes, add a short ADR under `docs/adr/` with:

1. Context
2. Decision
3. Consequences

Suggested filename format: `YYYY-MM-DD-short-title.md`.

## Change Process

Before changing architecture-level behavior:

- Update this guide (or add an ADR) in the same PR.
- Keep README summaries brief and link back to this document.
- Avoid introducing cross-role coupling without an explicit documented reason.
