# Local PDF Preview Contract

`GET /sources/{source_id}/pdf` serves an already-ingested PDF from the backend's local corpus files. It does not contact the source website.

## Successful response

- `200 OK`, `Content-Type: application/pdf`
- `Content-Disposition: inline; filename="source.pdf"`
- Supports byte-range requests for browser PDF viewers.
- The source must have `acquisition_enabled: true`, `license_review_status: verified`, `format: pdf`, `source_kind: unstructured`, an allowed sensitivity, and `retrieval` in `allowed_usage`.
- The server resolves `source_id` through `data/manifests/sources.yaml`, confines the path to `data/raw/reports/`, and verifies the file against the manifest SHA-256 before serving it.
- The browser uses the endpoint as the iframe URL and places page/search fragments on that URL. No filesystem path is accepted from the request.

## Errors

Both errors use the versioned API error envelope:

```json
{
  "schema_version": "1.0",
  "error_code": "SOURCE_NOT_FOUND",
  "message": "The requested PDF source is unavailable."
}
```

- `404 SOURCE_NOT_FOUND`: the source is unknown or not approved for retrieval.
- `503 SOURCE_FILE_UNAVAILABLE`: the registry, local file, path, or checksum is invalid or unavailable. Internal paths and validation details are not returned.
