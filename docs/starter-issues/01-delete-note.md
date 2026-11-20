# Add an endpoint to delete a note

Add `DELETE /notes/{note_id}`.

- Returns 204 with no body when the note existed and was deleted.
- Returns 404 when the note doesn't exist, like `GET /notes/{note_id}`.
- After a delete, `GET /notes/{note_id}` returns 404 and the note no longer appears in `GET /notes`.
- Add tests for both cases.
