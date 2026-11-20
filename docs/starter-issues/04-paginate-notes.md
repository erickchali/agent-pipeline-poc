# Paginate the notes list

Add `limit` and `offset` query parameters to `GET /notes`.

- `limit` defaults to 50, must be between 1 and 100. Out-of-range values return 422.
- `offset` defaults to 0 and can't be negative.
- Works together with the existing ordering by id.
- Add tests for defaults, a second page, and invalid values.
