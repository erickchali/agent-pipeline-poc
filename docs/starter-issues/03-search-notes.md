# Search notes by title

Add an optional `q` query parameter to `GET /notes`.

- `GET /notes?q=meet` returns only notes whose title contains "meet", case-insensitive.
- Without `q`, behavior is unchanged.
- Keep the existing ordering by id.
- Add tests for a match, no match, and mixed case.
