# 🔒 Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability:

1. **Do NOT** open a public GitHub issue
2. Open a [GitHub Security Advisory](https://github.com/tomekdot/pursuit-maps/security/advisories/new) instead
3. Or contact the maintainer directly

## What This Project Does NOT Do

- Does not collect or store personal user data
- Does not execute arbitrary code from external sources
- API keys (GAS_WEBAPP_URL) are stored only as GitHub Secrets or local files, never in code

## GAS Web App Security

- Deployed as "Execute as me" — runs under your Google account
- "Anyone" access means anyone can call the URL, but it only accepts structured JSON payloads
- For production use, switch to "Only me" and add API key validation in the GAS script
