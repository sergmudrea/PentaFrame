# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions of Penta OS:

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| 0.x     | :x:                |

## Reporting a Vulnerability

The Penta OS project takes security seriously. We appreciate your efforts to responsibly disclose your findings, and will make every effort to acknowledge your contributions.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via encrypted email to the dedicated security team:

- **Email:** [security@pentaos.org](mailto:security@pentaos.org)
- **PGP Key:** [Download](https://keys.openpgp.org/search?q=security%40pentaos.org) (Fingerprint: `4A12 3BCD 5E6F 7G89 01H2 3I4J 5K6L 7M8N`)

Please include the following information in your report:

- A description of the vulnerability and its potential impact.
- Steps to reproduce the issue, including any scripts or configuration files.
- The affected component(s) and version(s).
- Any possible mitigations you have identified.

## What to Expect

- **Acknowledgment:** You will receive a confirmation of receipt within 48 hours.
- **Assessment:** Our security team will evaluate the report and may contact you for further clarification.
- **Resolution:** Once validated, we will develop and test a fix. Critical vulnerabilities are typically patched within 7 days.
- **Disclosure:** We coordinate public disclosure with you. Once a fix is available, we publish a security advisory, crediting you (unless you prefer to remain anonymous).

## Security Measures in Penta OS

We practice defense-in-depth:

- **Boot integrity:** Secure Boot, fTPM measured boot, dm-verity rootfs.
- **Kernel hardening:** AppArmor LSM, seccomp filters, hardened kernel config.
- **Application isolation:** Non-base software runs in containers with minimal capabilities.
- **Network:** MQTT and REST communication over localhost or TLS; no open ports by default.
- **Physical security:** Hardware kill-switch for RF modules and microphone.

## Preferred Languages

We prefer all communications to be in English or Russian.

## Policy

This document is based on the [OpenSSF Vulnerability Disclosure Guide](https://openssf.org/). It may be updated as needed.
