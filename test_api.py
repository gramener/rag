# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "duckdb",
#     "fastapi",
#     "httpx",
#     "langchain-community~=0.3.0",
#     "langchain-openai~=0.2.0",
#     "langchain~=0.3.0",
#     "pydantic",
#     "pymupdf",
#     "python-multipart",
#     "uvicorn",
#     "reportlab",
#     "pytest",
#     "pytest-asyncio",
# ]
# ///
import pytest
from fastapi.testclient import TestClient
from main import app
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.pdfgen import canvas
import sys

client = TestClient(app)

# Mock external API responses
@pytest.fixture(autouse=True)
def mock_external_api(monkeypatch):
    async def mock_forward_request(url, method, token, **kwargs):
        if "collections" in url and method == "GET":
            return {"total": 1, "collections": [{"id": "test_id", "name": "Test Collection"}]}
        elif "collections" in url and method == "POST":
            return {"id": "new_collection_id", "name": "New Collection"}
        elif "documents" in url and method == "POST":
            return {"file_id": "new_file_id", "status": "indexed"}
        elif "search" in url:
            return {"results": [], "total": 0, "processing_time": "0.1s"}
        return {}

    monkeypatch.setattr("main.forward_request", mock_forward_request)

@pytest.fixture
def sample_collection():
    return {
        "name": "Test Collection",
        "authors": ["Test Author"],
        "extraction_strategy": {"pdf": "PyMuPDF4LLM", "html": "to_md", "docx": "to_md"},
        "embedding_model": "text-embedding-3-small"
    }

@pytest.fixture
def create_test_collection():
    def _create_collection(name="Test Collection"):
        headers = {"Authorization": "Bearer test_token"}
        collection_data = {
            "name": name,
            "authors": ["Test Author"],
            "extraction_strategy": {"pdf": "PyMuPDF4LLM", "html": "to_md", "docx": "to_md"},
            "embedding_model": "text-embedding-3-small"
        }
        response = client.post("/v1/collections", json=collection_data, headers=headers)
        assert response.status_code == 201
        return response.json()["id"]
    return _create_collection

def create_pdf(content):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, content)
    pdf.save()
    buffer.seek(0)
    return buffer

def add_test_document(collection_id, content="test content"):
    headers = {"Authorization": "Bearer test_token"}
    pdf_content = create_pdf(content)
    files = {"file": ("test.pdf", pdf_content, "application/pdf")}
    response = client.post(f"/v1/collections/{collection_id}/documents", files=files, headers=headers)
    assert response.status_code == 201
    return response.json()["file_id"]

@pytest.mark.asyncio
async def test_list_collections():
    headers = {"Authorization": "Bearer test_token"}
    response = client.get("/v1/collections", headers=headers)
    print(response.headers)
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "collections" in data

@pytest.mark.asyncio
async def test_create_collection(sample_collection):
    headers = {"Authorization": "Bearer test_token"}
    response = client.post("/v1/collections", json=sample_collection, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data

@pytest.mark.asyncio
async def test_update_collection(create_test_collection):
    collection_id = create_test_collection()
    headers = {"Authorization": "Bearer test_token"}
    update_data = {"authors": ["New Author"]}
    response = client.patch(f"/v1/collections/{collection_id}", json=update_data, headers=headers)
    assert response.status_code == 200
    updated_collection = response.json()
    assert updated_collection["authors"] == ["New Author"]
    assert updated_collection["id"] == collection_id

@pytest.mark.asyncio
async def test_delete_collection(create_test_collection):
    collection_id = create_test_collection()
    headers = {"Authorization": "Bearer test_token"}
    response = client.delete(f"/v1/collections/{collection_id}", headers=headers)
    assert response.status_code == 204
    get_response = client.get(f"/v1/collections/{collection_id}", headers=headers)
    assert get_response.status_code == 404

@pytest.mark.asyncio
async def test_add_document(create_test_collection):
    collection_id = create_test_collection()
    file_id = add_test_document(collection_id)
    assert file_id is not None

@pytest.mark.asyncio
async def test_delete_document(create_test_collection):
    collection_id = create_test_collection()
    file_id = add_test_document(collection_id)
    headers = {"Authorization": "Bearer test_token"}
    response = client.delete(f"/v1/collections/{collection_id}/documents/{file_id}", headers=headers)
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_vector_search(create_test_collection):
    collection_id = create_test_collection()

    # Add documents with clear relevance distinction
    docs = [
        "The quick brown fox jumps over the lazy dog",
        "Foxes are known for their cunning nature and bushy tails",
        "Mount Everest is the highest peak in the world",
        "The Rocky Mountains stretch from Canada to New Mexico"
    ]
    for doc in docs:
        add_test_document(collection_id, doc)

    headers = {"Authorization": "Bearer test_token"}
    response = client.get(f"/v1/collections/{collection_id}/search?q=fox&n=5", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert "results" in data
    assert "total" in data
    assert "processing_time" in data
    assert len(data["results"]) == 2  # Only two documents should be returned

    # Verify that relevant documents are included
    relevant_docs = docs[:2]  # The first two documents are about foxes
    for doc in relevant_docs:
        assert any(doc in result["content"] for result in data["results"]), f"'{doc}' should be in the results"

    # Verify that irrelevant documents are not included
    irrelevant_docs = docs[2:]  # The last two documents are about mountains
    for doc in irrelevant_docs:
        assert all(doc not in result["content"] for result in data["results"]), f"'{doc}' should not be in the results"

    # Check if results are sorted by score in descending order
    scores = [result["score"] for result in data["results"]]
    assert scores == sorted(scores, reverse=True), "Results are not sorted by score in descending order"

    # Verify that both results contain "fox" or "foxes"
    assert all("fox" in result["content"].lower() for result in data["results"]), "All results should contain 'fox' or 'foxes'"

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
            "embedding_model": "text-embedding-3-small"
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
        "embedding_model": "text-embedding-3-small"
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
        "embedding_model": "text-embedding-3-small"
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
    pytest_args = ["-v", "test_api.py"] + sys.argv[1:]
    pytest.main(pytest_args)
