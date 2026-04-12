# Day 4 Homework — ChromaDB Search & Filter Exercises

**Topic:** Metadata Filtering · Full Text Search · Combined Queries
**Estimated time:** ~40 minutes · individual or pairs

## Overview

Practice ChromaDB's filtering capabilities using a shared knowledge base — a fictional university IT helpdesk with 18 documents across 6 categories. All exercises use the same starter file (`4.2-homerwork-starter.py`). Only add code in the marked `TODO` sections; do not modify the setup above them.

## Setup

```bash
pip install chromadb
python 4.2-homerwork-starter.py
```

## The Knowledge Base

18 documents split across 6 categories, each with the following metadata:

| Field      | Type    | Values                                              |
|------------|---------|-----------------------------------------------------|
| `category` | string  | `"vpn"`, `"email"`, `"software"`, `"network"`, `"accounts"`, `"printing"` |
| `priority` | string  | `"high"`, `"medium"`, `"low"`                       |
| `year`     | integer | `2024` or `2025`                                    |
| `verified` | boolean | `True` or `False`                                   |

## Quick Reference

```python
# Direct fetch — no similarity ranking
collection.get(where={"field": "value"})                        # exact match
collection.get(where={"field": {"$gt": 5}})                     # numeric comparison
collection.get(where={"$and": [{...}, {...}]})                   # combine filters
collection.get(where_document={"$contains": "word"})            # text contains
collection.get(where_document={"$not_contains": "word"})        # text does not contain

# Semantic similarity search + optional filters
collection.query(
    query_texts=["your question here"],
    n_results=3,
    where={"field": "value"},                   # optional metadata filter
    where_document={"$contains": "word"},       # optional text filter
    include=["documents", "metadatas", "distances"]
)
```

---

## Exercises

### Exercise 1 — Basic Metadata Filter
**Concept:** `where` with a simple equality filter on `collection.get()`

Retrieve all documents where `category == "vpn"` using a `where` filter.
**Expected:** 3 documents — `doc-000`, `doc-001`, `doc-002`

---

### Exercise 2 — Combined Metadata Filters
**Concept:** `$and` and `$or` logical operators

**Task A:** Retrieve documents where `priority == "high"` AND `year == 2025` AND `verified == True`.
**Expected:** 7 documents spanning vpn, email, network, and accounts categories

**Task B (Extension):** Retrieve documents where `category == "software"` OR `category == "printing"`.
**Expected:** 6 documents

---

### Exercise 3 — Full Text Search
**Concept:** `where_document` with `$contains` and `$not_contains`

> Note: `$contains` is a substring match — it finds the exact string, not semantic meaning.

**Task A:** Find all documents whose text contains the word `"student"`.

**Task B (Extension):** Narrow results to documents that contain `"student"` but do NOT contain `"password"`. Compare the count to Task A — how many were excluded?

---

### Exercise 4 — Semantic Query + Combined Filters
**Concept:** `collection.query()` (semantic search) combined with both `where` and `where_document`

Run a semantic query for `"how do I print documents on campus"` restricted to:
- `category == "printing"` (using `where`)
- Document text must contain `"page"` (using `where_document`)
- Request `n_results=5` and include distances

**Reflection questions:**
- How many results are returned? Why might it be fewer than `n_results=5`?
- Are the distance values close to 0 or far from 0? What does that tell you?
- Remove the `where` filter and run again — how does the result set change?

---

## Bonus Challenges

1. Use `$gte` to find all documents from `year >= 2025`
2. Use `$in` to find documents where `priority` is `"high"` or `"medium"`
3. Combine metadata and text filters: find high-priority documents containing the word `"MFA"`
4. Use `collection.get(include=[])` to retrieve only document IDs (no text, no metadata) — when is this useful?
