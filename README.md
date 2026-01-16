# TheoWiki

TheoWiki is a data-driven web application for structured theological knowledge.

The project models theologians, works, topics, and their relationships as explicit data and renders them as a fast, static-first website. The emphasis is on **schema design, data normalization, and deterministic indexing**, not prose content.

**Live site:** https://theo-wiki.klosoter.com

---

## What This Project Demonstrates

From a software perspective, TheoWiki focuses on:

- Designing a **non-trivial domain model**
- Managing **structured, evolving datasets**
- Building **deterministic data pipelines**
- Serving complex reference data with minimal runtime overhead

Theology is the domain.  
The underlying engineering problems are general.

---

## Project Structure

```
.
├── public/
│   └── data/               # Generated JSON datasets (topics, works, indices)
├── static/
│   ├── vendor/             # Vendored JS libraries (React, ReactDOM, Babel)
│   └── style.css           # Site styling
├── utils.py                # Data loading / indexing helpers
├── requirements.txt        # Python dependencies
├── Dockerfile              # Containerized build/runtime
├── fly.toml                # Deployment configuration (Fly.io)
└── README.md
```

Design principle: **domain complexity lives in data, not application logic**.

---

## Data Model (High Level)

TheoWiki is organized around four core primitives:

- **Theologians** — canonical figures with stable identifiers  
- **Works** — books, essays, and collected writings  
- **Topics** — doctrinal loci and sub-questions  
- **Relations** — explicit edges (author → work, work → topic, topic ↔ topic)

All entities are:
- normalized
- addressable by stable IDs
- indexable without heuristics

Derived indices are generated deterministically.

---

## Architecture

- Static-first site backed by structured JSON
- Minimal backend logic
- Explicit separation between:
  - data
  - indexing utilities
  - presentation
- Containerized for reproducible builds
- Deployed via Fly.io

This avoids runtime databases, CMS abstractions, and implicit relationships.

---

## Data Generation Notes

Some datasets in this project were initially generated or augmented using
large language models (LLMs) as part of an offline preprocessing workflow.

LLM usage is confined to a separate experimental repository and is not
required to build, run, or deploy this site. All data published here is
stored as static artifacts and reviewed before inclusion.

---

## Recruiter Context

This repository demonstrates:

- Translating complex domain knowledge into **formal schemas**
- Designing systems with **clarity and traceability**
- Handling real, messy reference data
- Building for **evolution without data corruption**
- Shipping and deploying a real, publicly accessible system

Domain-specific content, general engineering problems.

---

## Status

Active development.  
Schemas and datasets evolve; breaking changes may occur.

---

## License

MIT

---

## Author

Mark  
Systematic theology · biblical linguistics · NLP / data engineering
