# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately. Do not open a public issue, pull request or discussion.

- GitHub private vulnerability reporting: open the **Security** tab of this repository and choose **Report a vulnerability**.
- Or email support@didit.me with "Security" in the subject.

## What to include

- The affected SDK version (`python -c "import didit; print(didit.__version__)"`) and Python version.
- A description of the issue and its impact.
- Steps or a minimal script to reproduce it.
- Any request id, log line or proof of concept that helps, with API keys, secrets, tokens and personal data removed.

## What to expect

We will acknowledge your report, keep you informed while we investigate, and tell you when a fix is released.
Please give us reasonable time to fix the issue before you disclose it publicly.
We are glad to credit you in the advisory if you wish.

## Supported versions

Security fixes go into the latest minor release of `didit-sdk`.
Upgrade to it to receive them.

## Scope

This policy covers this SDK (the code in this repository).
Vulnerabilities in the Didit API, the Didit dashboards or other Didit services are welcome too: report them to the same address, support@didit.me.
