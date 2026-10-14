# Security Policy

VentureScout takes the security and integrity of its data pipeline, discovery engine, and web application seriously. We appreciate the responsible disclosure of any security vulnerabilities by researchers and contributors.

## Supported Versions

VentureScout is an open-source project following a rolling release model deployed via GitHub Pages and containerized/self-hosted environments.

| Version / Branch | Supported | Description |
|---|---|---|
| `main` | :white_check_mark: Yes | Actively maintained; receives security fixes and updates. |
| Historical branches / tags | :x: No | Not maintained with security backports. |

If you discover a vulnerability, please verify that it reproduces on the latest commit of the `main` branch.

## Reporting a Vulnerability

Please **do not** open public GitHub issues, pull requests, or public discussions for suspected security vulnerabilities. Publicly disclosing an unpatched flaw puts self-hosted instances and deployments at risk.

### Reporting Channel

Suspected security vulnerabilities should be reported privately through GitHub's native **Private Vulnerability Reporting**:

1. Navigate to the repository's **Security** tab on GitHub:
   [`https://github.com/BagofRamen27/Venture-capital-tracker-/security`](https://github.com/BagofRamen27/Venture-capital-tracker-/security)
2. Under "Vulnerability reporting", click **"Report a vulnerability"** (or visit [`/security/advisories/new`](https://github.com/BagofRamen27/Venture-capital-tracker-/security/advisories/new)).
3. Fill out the advisory form with detailed reproduction steps and submit the draft advisory.

> **Important Notice on Feature Availability:**
> Private Vulnerability Reporting requires explicit repository-side activation by the repository maintainer (`Settings → Code security and analysis → Private vulnerability reporting → Enable`). If the "Report a vulnerability" button is not visible on GitHub, this repository-side setting has not yet been enabled.
>
> In that event, **do not** report the vulnerability via public issue tracker, pull request, or public comments. Please allow the repository maintainer to configure the private reporting channel before disclosing technical vulnerability details.

## What to Include in a Report

To help us triage and investigate the issue efficiently, please provide:

- **Component:** The affected component (`discovery-engine`, `vc-investment-tracker-web`, API endpoints, or CI workflows).
- **Vulnerability Type:** A description of the issue (e.g., credential exposure, unauthenticated information disclosure, injection, cross-site scripting).
- **Proof of Concept:** Step-by-step reproduction instructions or a minimal test case demonstrating the vulnerability.
- **Impact Assessment:** The potential impact on data confidentiality, integrity, or system availability.
- **Proposed Fix:** Any suggested patch or remediation code, if available.

> **Safety Reminder:** When submitting logs, request bodies, or test configurations, **never** include real production credentials, live API keys, personal access tokens, or private environment values. Always use synthetic placeholders (e.g., `FAKE_TOKEN_DO_NOT_USE`).

## Coordinated Disclosure Process

1. **Acknowledgment & Verification:** The maintainer will review the advisory and verify the reported behavior.
2. **Remediation:** A patch will be developed in a private temporary fork or dedicated security branch.
3. **Release & Announcement:** Once the fix is verified, a release will be merged into `main`, and the security advisory will be published with proper credit to the reporter.

We ask reporters to maintain confidentiality until a patch has been merged and coordinated disclosure is complete.
