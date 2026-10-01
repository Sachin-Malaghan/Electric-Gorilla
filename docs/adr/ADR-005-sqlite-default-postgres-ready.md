# ADR-005: SQLAlchemy store - SQLite by default, PostgreSQL in deployment; hashed embeddings before pgvector

**Decision.** The structured store uses SQLAlchemy Core with one table per entity (indexed lookup columns + the full document as JSON) and an append-only `events` table. `DATABASE_URL` selects PostgreSQL; with nothing set it uses a local SQLite file in WAL mode. Semantic retrieval uses a deterministic hashing embedder kept in memory behind `IEmbedder`.

**Reason.** The studio must run on a developer PC with nothing installed (this machine has no Docker). The spec makes PostgreSQL the source of truth and pgvector the first vector store; both are a configuration change away, not a rewrite.

**Alternatives.** PostgreSQL only; an ORM with relational columns for every field; a dedicated vector database.

**Trade-offs.** JSON documents trade ad-hoc SQL reporting for schema flexibility while the model is still moving. Hashing embeddings are lexical, not truly semantic - good enough next to the symbol and graph retrievers, and replaceable.

**Affected systems.** `shunya/core/persistence/`, `shunya/knowledge/`.
