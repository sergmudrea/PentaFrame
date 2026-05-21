# Contributing to Penta OS

First off, thank you for considering contributing to Penta OS! It's people like you that make this project possible.

The following is a set of guidelines for contributing to Penta OS. These are mostly guidelines, not rules. Use your best judgment, and feel free to propose changes to this document in a pull request.

## Code of Conduct

This project and everyone participating in it is governed by the [Penta OS Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to [conduct@pentaos.org](mailto:conduct@pentaos.org).

## How Can I Contribute?

### Reporting Bugs

- **Ensure the bug was not already reported** by searching on GitHub under [Issues](https://github.com/penta-os/core/issues).
- If you're unable to find an open issue addressing the problem, [open a new one](https://github.com/penta-os/core/issues/new/choose). Be sure to include a **title and clear description**, as much relevant information as possible, and a **code sample** or an **executable test case** demonstrating the expected behavior that is not occurring.
- Use the bug report template to provide the steps to reproduce, expected outcome, actual outcome, and environment details (Penta OS version, hardware platform, etc.).

### Suggesting Enhancements

- Open a new issue using the feature request template.
- Clearly describe the feature, the motivation behind it, and how it should work.
- Include examples and mockups if applicable.

### Your First Code Contribution

Unsure where to begin? Look for issues labeled `good first issue` or `help wanted`. These are tasks we've identified as suitable for newcomers.

### Pull Requests

1. Fork the repository and create your branch from `main`.
2. If you've added code, add tests. Ensure the test suite passes.
3. If you've changed APIs, update the documentation.
4. Make sure your code lints (we use `pylint` and `shellcheck`).
5. Follow the [style guides](#style-guides).
6. Issue the pull request. Include a clear description of the problem and solution, and reference any related issue.

### Development Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/penta-os/core.git
   cd core

Install required dependencies:
bash

sudo apt install -y python3-pip python3-venv podman distrobox qemu-user-static binfmt-support shellcheck
pip install -r requirements.txt

For building Penta OS images, refer to BUILDING.md.

Run the test suite:
bash

make test

Style Guides

    Python: Follow PEP 8. Use type hints where possible. Format with black.

    Bash: POSIX-compliant, verify with shellcheck.

    QML: Follow Qt's QML coding conventions. Use Qt 6.

    Documentation: Write in clear, concise English. Use Markdown.

Commit Messages

    Use the present tense ("Add feature" not "Added feature").

    Use the imperative mood ("Move cursor to..." not "Moves cursor to...").

    Limit the first line to 72 characters or less.

    Reference issues and pull requests liberally after the first line.

Testing

We use a combination of unit tests (Python pytest), integration tests (QEMU virtual machines), and hardware-in-the-loop tests. All new features must include corresponding tests.

Run unit tests locally:
bash

pytest tests/

For container-related tests, ensure Docker/Podman and Distrobox are installed and working.
Community

    Join our [Matrix/Discord] for real-time discussion.

    Participate in the decision-making process via GitHub Discussions.

License

By contributing, you agree that your contributions will be licensed under the GPL-3.0-or-later License as found in the LICENSE file.

Thank you for helping make Penta OS the universal computing platform!
