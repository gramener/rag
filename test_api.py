# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastapi",
#     "httpx",
#     "pytest",
#     "python-multipart",
#     "pytest-asyncio",
#     "reportlab",
# ]
# ///
import pytest
from fastapi.testclient import TestClient
from main import app
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.pdfgen import canvas


client = TestClient(app)

# Mock authentication
@pytest.fixture(autouse=True)
def mock_auth(monkeypatch):
    async def mock_get_current_user():
        return {"id": "test_user"}
    monkeypatch.setattr("main.get_current_user", mock_get_current_user)

@pytest.fixture
def sample_collection():
    return {
        "name": "Test Collection",
        "authors": ["Test Author"],
        "extraction_strategy": {"pdf": "PyMuPDF4LLM", "html": "to_md", "docx": "to_md"},
        "embedding_model": "text-embedding-003-small"
    }

def create_pdf(content):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, content)
    pdf.save()
    buffer.seek(0)
    return buffer

@pytest.mark.asyncio
async def test_list_collections():
    response = client.get("/v1/collections")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "collections" in data

@pytest.mark.asyncio
async def test_create_collection(sample_collection):
    response = client.post("/v1/collections", json=sample_collection)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == sample_collection["name"]
    assert "id" in data

@pytest.mark.asyncio
async def test_update_collection(sample_collection):
    # First, create a collection
    create_response = client.post("/v1/collections", json=sample_collection)
    collection_id = create_response.json()["id"]

    # Now, update it
    update_data = {"authors": ["New Author"]}
    response = client.patch(f"/v1/collections/{collection_id}", json=update_data)
    assert response.status_code == 200
    data = response.json()
    assert data["authors"] == update_data["authors"]

@pytest.mark.asyncio
async def test_delete_collection(sample_collection):
    # First, create a collection
    create_response = client.post("/v1/collections", json=sample_collection)
    collection_id = create_response.json()["id"]

    # Now, delete it
    response = client.delete(f"/v1/collections/{collection_id}")
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_add_document(sample_collection):
    # First, create a collection
    create_response = client.post("/v1/collections", json=sample_collection)
    collection_id = create_response.json()["id"]

    # Now, add a document
    pdf_content = create_pdf("test content")
    files = {"file": ("test.pdf", pdf_content, "application/pdf")}
    response = client.post(f"/v1/collections/{collection_id}/documents", files=files)
    assert response.status_code == 201
    data = response.json()
    assert "file_id" in data
    assert data["status"] == "indexed"

@pytest.mark.asyncio
async def test_delete_document(sample_collection):
    # First, create a collection and add a document
    create_response = client.post("/v1/collections", json=sample_collection)
    collection_id = create_response.json()["id"]
    files = {"file": ("test.pdf", b"test content", "application/pdf")}
    add_doc_response = client.post(f"/v1/collections/{collection_id}/documents", files=files)
    file_id = add_doc_response.json()["file_id"]

    # Now, delete the document
    response = client.delete(f"/v1/collections/{collection_id}/documents/{file_id}")
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_vector_search(sample_collection):
    # First, create a collection and add a document
    create_response = client.post("/v1/collections", json=sample_collection)
    collection_id = create_response.json()["id"]
    pdf_content = create_pdf("The quick brown fox jumps over the lazy dog")
    files = {"file": ("test.pdf", pdf_content, "application/pdf")}
    client.post(f"/v1/collections/{collection_id}/documents", files=files)

    # Now, perform a search
    response = client.get(f"/v1/collections/{collection_id}/search?q=fox&n=5")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "total" in data
    assert "processing_time" in data

@pytest.mark.asyncio
async def test_error_handling():
    # Test 404 error
    response = client.get("/v1/collections/non_existent_id")
    assert response.status_code == 404
    data = response.json()
    assert "message" in data
    assert "documentation_url" in data
    assert "status_code" in data

    # Test 400 error
    invalid_collection = {"invalid_field": "value"}
    response = client.post("/v1/collections", json=invalid_collection)
    assert response.status_code == 400
    data = response.json()
    assert "message" in data
    assert "documentation_url" in data
    assert "status_code" in data

@pytest.mark.asyncio
async def test_pagination_and_filtering():
    # Create multiple collections
    for i in range(15):
        client.post("/v1/collections", json={
            "name": f"Test Collection {i}",
            "authors": ["Test Author"],
            "extraction_strategy": {"pdf": "PyMuPDF4LLM"},
            "embedding_model": "text-embedding-003-small"
        })

    # Test pagination
    response = client.get("/v1/collections?page=2&per_page=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["collections"]) == 5

    # Test filtering by author
    response = client.get("/v1/collections?author=Test Author")
    assert response.status_code == 200
    data = response.json()
    assert all("Test Author" in collection["authors"] for collection in data["collections"])

    # Test filtering by creation date
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    response = client.get(f"/v1/collections?created_after={yesterday}")
    assert response.status_code == 200
    data = response.json()
    assert all(datetime.fromisoformat(collection["created_at"]) > datetime.fromisoformat(yesterday)
               for collection in data["collections"])

    # Test filtering by creation date range
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    today = datetime.now().isoformat()
    response = client.get(f"/v1/collections?created_after={yesterday}&created_before={today}")
    assert response.status_code == 200
    data = response.json()
    assert all(yesterday < collection["created_at"] < today for collection in data["collections"])

@pytest.mark.asyncio
async def test_search_parameters():
    # Create a collection and add a document
    collection = {
        "name": "Search Test Collection",
        "authors": ["Test Author"],
        "extraction_strategy": {"pdf": "PyMuPDF4LLM"},
        "embedding_model": "text-embedding-003-small"
    }
    create_response = client.post("/v1/collections", json=collection)
    collection_id = create_response.json()["id"]
    files = {"file": ("test.pdf", b"The quick brown fox jumps over the lazy dog", "application/pdf")}
    client.post(f"/v1/collections/{collection_id}/documents", files=files)

    # Test different search parameters
    response = client.get(f"/v1/collections/{collection_id}/search?q=fox&n=5&rerank_strategy=bm25&similarity_threshold=0.8&fuzzy=true")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) <= 5  # May be less if similarity threshold is applied

    # Test rerank_strategy parameter
    response = client.get(f"/v1/collections/{collection_id}/search?q=fox&rerank_strategy=bm25")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data

    # Test similarity_threshold parameter
    response = client.get(f"/v1/collections/{collection_id}/search?q=fox&similarity_threshold=0.9")
    assert response.status_code == 200
    data = response.json()
    assert all(result["score"] >= 0.9 for result in data["results"])

@pytest.mark.asyncio
async def test_invalid_token():
    # Test with an invalid token
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.get("/v1/collections", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "message" in data
    assert "documentation_url" in data
    assert data["status_code"] == 401

@pytest.mark.asyncio
async def test_invalid_collection_creation():
    # Test creating a collection with invalid data
    invalid_collection = {
        "name": "",  # Empty name should be invalid
        "authors": [],
        "extraction_strategy": {},
        "embedding_model": "invalid_model"
    }
    response = client.post("/v1/collections", json=invalid_collection)
    assert response.status_code == 400
    data = response.json()
    assert "message" in data
    assert "errors" in data
    assert any(error["field"] == "name" for error in data["errors"])

@pytest.mark.asyncio
async def test_search_with_invalid_parameters():
    # Create a collection for testing
    collection = {
        "name": "Test Collection",
        "authors": ["Test Author"],
        "extraction_strategy": {"pdf": "PyMuPDF4LLM"},
        "embedding_model": "text-embedding-003-small"
    }
    create_response = client.post("/v1/collections", json=collection)
    collection_id = create_response.json()["id"]

    # Test search with invalid n parameter
    response = client.get(f"/v1/collections/{collection_id}/search?q=test&n=0")
    assert response.status_code == 400
    data = response.json()
    assert "message" in data
    assert "errors" in data

    # Test search with invalid similarity_threshold
    response = client.get(f"/v1/collections/{collection_id}/search?q=test&similarity_threshold=2")
    assert response.status_code == 400
    data = response.json()
    assert "message" in data
    assert "errors" in data

@pytest.mark.asyncio
async def test_nonexistent_collection():
    nonexistent_id = "nonexistent_collection_id"

    # Test getting a nonexistent collection
    response = client.get(f"/v1/collections/{nonexistent_id}")
    assert response.status_code == 404

    # Test updating a nonexistent collection
    update_data = {"authors": ["New Author"]}
    response = client.patch(f"/v1/collections/{nonexistent_id}", json=update_data)
    assert response.status_code == 404

    # Test deleting a nonexistent collection
    response = client.delete(f"/v1/collections/{nonexistent_id}")
    assert response.status_code == 404

    # Test adding a document to a nonexistent collection
    files = {"file": ("test.pdf", b"test content", "application/pdf")}
    response = client.post(f"/v1/collections/{nonexistent_id}/documents", files=files)
    assert response.status_code == 404

    # Test searching in a nonexistent collection
    response = client.get(f"/v1/collections/{nonexistent_id}/search?q=test")
    assert response.status_code == 404

if __name__ == "__main__":
    pytest.main(["-v", "test_api.py"])
