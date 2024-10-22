# RAG API

This API is deployed at `https://rag.straive.app/`.

All API endpoints start with `/v1/`.

# Authentication

Use OAuth 2.0 for all requests. Include the access token in the `Authorization` header as `Bearer <token>`.

# Headers

- `Content-Type: application/json`
- `Authorization: Bearer <token>`

# Status Codes

- **200 OK**: Request successful.
- **201 Created**: Resource created successfully.
- **204 No Content**: Resource deleted successfully.
- **400 Bad Request**: Invalid input.
- **401 Unauthorized**: Authentication required.
- **403 Forbidden**: User lacks permissions.
- **404 Not Found**: Resource not found.
- **409 Conflict**: Resource conflict (e.g., duplicates).
- **500 Internal Server Error**: Unexpected server error.

# Consistent Error Response Structure

Every error response returns a JSON object with the following fields:

- **message**: Human-readable error description.
- **documentation_url**: Link to relevant documentation.
- **errors** (optional): List of error details, useful for validation errors.
- **status_code**: HTTP status code.

# Example Error Response

```json
{
  "message": "Validation Failed",
  "documentation_url": "https://rag.straive.app/docs/validation",
  "errors": [{ "field": "name", "message": "Name is required." }],
  "status_code": 400
}
```

## Endpoints

# 1. **List Collections**

```bash
GET /v1/collections
```

## Parameters

- `page` (optional): Page number (default: 1).
- `per_page` (optional): Results per page (default: 10).
- `author` (optional): Filter by author.
- `created_after` (optional): Filter by creation date.

## Response

```json
{
  "total": 100,
  "page": 1,
  "per_page": 10,
  "collections": [
    {
      "id": "123",
      "name": "Research Papers",
      "authors": ["Anand"],
      "created_at": "2024-01-15T12:34:56Z",
      "extraction_strategy": { "pdf": "PyMuPDF4LLM", "html": "to_md", "docx": "to_md" },
      "embedding_model": "text-embedding-003-small"
    }
  ]
}
```

## Error Response

- **400**: Bad request parameters.
- **401**: Unauthorized.

# 2. **Create a Collection**

```bash
POST /v1/collections
```

## Request Body

```json
{
  "name": "Research Papers",
  "authors": ["Anand"],
  "extraction_strategy": { "pdf": "PyMuPDF4LLM", "html": "to_md", "docx": "to_md" },
  "embedding_model": "text-embedding-003-small"
}
```

## Response

- **201 Created**

```json
{ "id": "123", "name": "Research Papers", "created_at": "2024-01-15T12:34:56Z" }
```

## Error Response

- **400**: Validation error (e.g., missing name).
- **401**: Unauthorized.
- **409**: Conflict (e.g., duplicate collection name).

# 3. **Update Collection Metadata**

```bash
PATCH /v1/collections/{collection_id}
```

## Request Body

```json
{ "authors": ["Anand", "Naveen"] }
```

## Response

- **200 OK**

```json
{ "id": "123", "name": "Research Papers", "authors": ["Anand", "Naveen"], "updated_at": "2024-01-20T15:45:00Z" }
```

## Error Response

- **400**: Validation error.
- **401**: Unauthorized.
- **404**: Collection not found.

# 4. **Delete a Collection**

```bash
DELETE /v1/collections/{collection_id}
```

- **204 No Content**

## Error Response

- **401**: Unauthorized.
- **403**: Forbidden (e.g., insufficient permissions).
- **404**: Collection not found.

# 5. **Add Documents to a Collection**

```bash
POST /v1/collections/{collection_id}/documents
```

## Request Body

Use `multipart/form-data` to upload files.

- `file` (required): File to be added.
- Automatically re-indexes the collection.

## Response

- **201 Created**

```json
{ "file_id": "456", "file_name": "document.pdf", "status": "indexed" }
```

## Error Response

- **400**: Invalid file format or missing file.
- **401**: Unauthorized.
- **404**: Collection not found.

# 6. **Delete Documents from a Collection**

```bash
DELETE /v1/collections/{collection_id}/documents/{file_id}
```

- Automatically re-indexes the collection.

## Response

- **204 No Content**

## Error Response

- **401**: Unauthorized.
- **403**: Forbidden (e.g., insufficient permissions).
- **404**: Document not found.

# 7. **Vector Search**

```bash
GET /v1/collections/{collection_id}/search?q={query}
```

## Parameters

- `q` (required): Query string.
- `n` (optional): Number of matches (default: 10).
- `rerank_strategy` (optional): Re-ranking strategy.
- `similarity_threshold` (optional): Threshold for results (default: 0.7).
- `fuzzy` (optional): Enable fuzzy matching (default: false).

## Response

```json
{
  "results": [
    {
      "document_id": "456",
      "text": "The quick brown fox jumps over the lazy dog.",
      "score": 0.95,
      "metadata": { "file_name": "document.pdf", "collection_id": "123" }
    }
  ],
  "total": 1,
  "processing_time": "0.120s"
}
```

## Error Response

- **400**: Invalid query parameter.
- **401**: Unauthorized.
- **404**: Collection not found.

# Example cURL Commands

## Create a Collection

```bash
curl -X POST /v1/collections \ -H "Authorization: Bearer <token>" \ -H "Content-Type: application/json" \ -d '{ "name": "Research Papers", "authors": ["Anand"], "extraction_strategy": { "pdf": "PyMuPDF4LLM", "html": "to_md", "docx": "to_md" }, "embedding_model": "text-embedding-003-small" }'
```

## Error Response Example

```json
{
  "message": "Validation Failed",
  "documentation_url": "https://rag.straive.app/docs/validation",
  "errors": [{ "field": "name", "message": "Name is required." }],
  "status_code": 400
}
```

## Vector Search

```bash
GET /v1/collections/123/search?q=fox&n=5
```

## Error Response Example

```json
{
  "message": "Resource Not Found: Collection with ID '123' does not exist.",
  "documentation_url": "https://rag.straive.app/docs/resources",
  "status_code": 404
}
```

This revised documentation integrates consistent error handling across all endpoints, making the API predictable, user-friendly, and aligned with best practices.
