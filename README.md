# Trilith

Trilith is an open-source, language-agnostic context management layer designed specifically to govern, structure, and serve working memory for AI systems. By splitting agent context into three structured tiers (Semantic, Procedural, and Episodic), governing it with a pluggable relevancy and distraction-prevention engine, and enforcing strict privacy and scope rules at the data layer, Trilith gives developers a production-grade external memory system. Whether running as a local Model Context Protocol (MCP) server, as a native Python library, or as a centralized service exposed via gRPC and REST/JSON, Trilith enables agents in any language or technology framework to retrieve, write, and audit context reliably under token constraints.

## System Architecture

```text
                  +----------------------------------------------+
                  |              Client Application              |
                  |     (Python / TypeScript / Go / Custom)      |
                  +-----------------------+----------------------+
                                          |
                        gRPC / REST / Stdio (MCP)
                                          |
                                          v
                  +----------------------------------------------+
                  |            Trilith Server Gateway            |
                  |                (trilith serve)               |
                  +-----------------------+----------------------+
                                          |
                                          v
                  +----------------------------------------------+
                  |                  Governor                    |
                  |    - Assemble contexts (budgeted tokens)     |
                  |    - Pluggable Scorer (TF-IDF/Embeddings)    |
                  |    - Distraction Penalty Filter              |
                  +-----------------------+----------------------+
                                          |
                                          v
                  +----------------------------------------------+
                  |               Privacy Engine                 |
                  |   - Scope Checking                           |
                  |   - PII Regex Redacting                      |
                  |   - Timestamps & Expiry Filter               |
                  +-----------------------+----------------------+
                                          |
            +-----------------------------+-----------------------------+
            |                             |                             |
            v                             v                             v
+-------------------------+   +-------------------------+   +-------------------------+
|      Semantic Store     |   |    Procedural Store     |   |     Episodic Store      |
| (SQLite/Vector DB back) |   | (Task steps & step fold)|   | (Tenant scopes & purge) |
+-------------------------+   +-------------------------+   +-------------------------+
```

## Quick Start (Installation Placeholder)

```bash
# Install trilith-core package
pip install trilith-core

# Start the gRPC and HTTP context services locally
trilith serve --host 127.0.0.1 --port 50051

# Or run via Docker
docker run -p 50051:50051 -p 8080:8080 trilith:latest
```

For more documentation, see the [docs/](docs/) directory.

## License

Trilith is distributed under the Apache License 2.0. See [LICENSE](LICENSE) for more details.