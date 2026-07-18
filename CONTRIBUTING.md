# Contributing to Trilith

First off, thank you for considering contributing to Trilith! We welcome contributions of all forms: new features, bug fixes, documentation, examples, and bug reports.

## Local Development Setup

Trilith uses a Python library as its core reference implementation, along with gRPC and HTTP interfaces.

### Prerequisites
- Python 3.10+
- Poetry or pip
- protoc (Protocol Buffer compiler)

### Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/Umairkhan2324/trilith.git
   cd trilith
   ```
2. Set up the Python virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```
3. Run tests using pytest:
   ```bash
   pytest
   ```

## Pull Request Process

1. Fork the repo and create your branch from `main`.
2. Ensure your changes are formatted properly using ruff. Run linting checks:
   ```bash
   ruff check .
   ruff format --check .
   ```
3. Make sure all unit tests pass:
   ```bash
   pytest
   ```
4. Submit a Pull Request targeting the `main` branch.
