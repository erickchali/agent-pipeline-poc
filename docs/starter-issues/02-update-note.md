# Allow partial updates to a note

Add `PATCH /notes/{note_id}`.

- The body may contain `title`, `body`, or both. Fields left out stay unchanged.
- The same validation as create applies: `title` must be 1–200 characters if present.
- Returns the updated note, or 404 if it doesn't exist.
- Add tests for updating one field, both fields, an invalid title and a missing note.
