# Security Policy

> 中文版：[`SECURITY_zh.md`](SECURITY_zh.md)

## Supported versions

Security fixes target the current code on the default branch. We do not commit
to separately maintaining historical commits, personal forks, unmerged branches
or unmodified third-party components; if the issue originates from a
third-party dependency, we will track the impact and follow upstream fixes.
This project does not yet commit to a fixed response SLA or long-term support
versions.

## Private vulnerability reporting

Please use the GitHub repository's **Private vulnerability reporting** to create
a private security report:

`Security` → `Advisories` → `Report a vulnerability`

If the repository does not currently show that entry, do not open a public
issue, and do not disclose exploit details in Discussions, PRs, logs or
screenshots. Wait for the maintainer to enable the private reporting entry
before submitting.

Where possible, the report should include:

- The affected commit, version, platform and configuration;
- Minimal reproducible steps, expected result and actual result;
- Impact scope, attack prerequisites and any mitigations you have already
  verified;
- Fully redacted logs, screenshots or proof-of-concept;
- Whether the issue has already been reported to the third-party dependency's
  maintainers.

Do not submit real API keys, tokens, passwords, cookies, personal data,
production databases or exploit code that could directly harm users. If a key
has already been exposed, revoke and rotate it at the provider first, then
report the repository issue.

## Handling

The maintainers will confirm the issue, verify the impact, coordinate the fix
and testing inside a private channel, and publish a security advisory when
appropriate. Please avoid public disclosure before a fix or mitigation is
released. Specific priority and release timing depend on impact,
reproducibility and fix risk; no unfulfillable SLA is offered.

## Security boundaries

- Keys are loaded only from environment variables or Git-ignored
  `${ELFIE_HOME}/config.yaml` / `.env`;
- Example configs may only contain obvious placeholder values, never real
  credentials;
- `~/.elfienest/` (or `ELFIE_HOME`) is the production data boundary; never
  commit its contents to the repository;
- Godot WebSocket, code execution, the file system and desktop process
  supervision are explicit security boundaries and must not be bypassed through
  debug entry points;
- The repository uses the official Gitleaks pre-commit hook to scan for
  hardcoded secrets; never bypass it with `--no-verify`.

For ordinary defects, please use the normal issue template; only
vulnerabilities, credential exposure or issues with security impact go through
the private security reporting channel.
