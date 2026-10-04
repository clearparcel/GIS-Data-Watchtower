# Security Policy

## Supported versions

Until the first stable release, security fixes are applied to the current `main` branch.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Report security concerns privately to the repository owner through GitHub's private vulnerability reporting feature when enabled, or through the ClearParcel contact channel published on the project website.

Include the affected version/commit, reproduction details, impact, and any suggested mitigation. Do not include secrets or sensitive provider data in reports.

## Deployment guidance

The dashboard is private by default. Do not expose it through a wildcard or Internet-facing bind without authentication and appropriate TLS/reverse-proxy controls. Keep credentials in environment variables or a secrets manager, never in configuration committed to Git.
