# Phase 3.6 - RAG Retrieval Quality

## Objective

Improve RAG performance for exact finance questions such as:

- What was the latest revenue?
- What were net sales?
- What was net income?
- What was operating cash flow?

Semantic retrieval alone can miss these answers because financial metrics are often stored in dense tables and exact line items.

## What Changed

Phase 3.6 adds:

- Finance query expansion
- Hybrid retrieval: semantic search plus keyword scoring
- Document-scoped RAG Q&A
- Revenue / net sales metric extraction
- A metric-first answer path before falling back to Groq

## Why This Matters

Embeddings are good at meaning, but weaker at exact numeric lookup.

For example:

```text
User: What was Apple's latest revenue?
```

The filing may use:

```text
Net sales 416,161 391,035 383,285
```

A semantic-only retriever may not connect "latest revenue" to "net sales" inside a financial statement table. Hybrid retrieval expands the query and boosts chunks that contain financial statement terms and numbers.

## Architecture

```mermaid
flowchart LR
    Question[User Question] --> Expand[Finance Query Expansion]
    Expand --> Semantic[Semantic Retrieval]
    Expand --> Keyword[Keyword Retrieval]
    Semantic --> Merge[Merge Results]
    Keyword --> Merge
    Merge --> Metric[Metric Extractor]
    Metric --> Answer[Exact Metric Answer]
    Merge --> Groq[Fallback Cited RAG Answer]
```

## Current Metric Support

The first metric extractor supports:

- revenue
- sales
- net sales
- total revenue

It looks for likely filing patterns such as:

```text
Net sales 416,161 391,035 383,285
Total revenue 100,000 90,000 80,000
```

## Limitations

This is still not full XBRL parsing.

Known limitations:

- Some SEC tables may flatten poorly.
- Units may be inferred from nearby words such as `in millions`.
- The extractor currently focuses on revenue / net sales.
- Future phases should parse XBRL facts directly.

## Suggested Exercises

1. Ask: `What was the latest revenue?`
2. Ask: `What were net sales?`
3. Compare the retrieved sources with the answer.
4. Add extractors for net income and operating cash flow.
5. Add table-aware parsing or XBRL extraction.
