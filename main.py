# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "chromadb",
#     "fastapi",
#     "httpx",
#     "langchain-community~=0.3.0",
#     "langchain-openai~=0.2.0",
#     "langchain~=0.3.0",
#     "pydantic",
#     "pymupdf",
#     "python-multipart",
#     "uvicorn",
# ]
# ///
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File, Header
from fastapi.responses import JSONResponse
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import httpx
import json
import os
import shutil
import sqlite3
import tempfile
import uuid

app = FastAPI(title="RAG API", version="1.0.0")

async def get_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    return authorization.split()[1]

async def forward_request(url: str, method: str, token: str, **kwargs):
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        response = await client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.json())
        return response.json()

def get_db():
    db = sqlite3.connect("collections.db")
    db.row_factory = sqlite3.Row
    return db

with get_db() as db:
    db.execute("CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, data JSON)")

class ErrorResponse(BaseModel):
    message: str
    documentation_url: str
    errors: Optional[List[Dict[str, str]]] = None
    status_code: int

class Collection(BaseModel):
    id: str
    name: str
    authors: List[str]
    created_at: datetime
    extraction_strategy: Dict[str, str]
    embedding_model: str
    # Add any future fields here

class CollectionCreate(BaseModel):
    name: str = Field(..., description="The name of the collection")
    authors: List[str] = Field(..., description="List of authors for the collection")
    extraction_strategy: Dict[str, str] = Field(..., description="Extraction strategy details")
    embedding_model: str = Field(..., description="The embedding model to use")
    # Add any future fields here

class CollectionUpdate(BaseModel):
    # All fields are optional for updates
    name: Optional[str] = None
    authors: Optional[List[str]] = None
    extraction_strategy: Optional[Dict[str, str]] = None
    embedding_model: Optional[str] = None
    # Add any future fields here

class DocumentResponse(BaseModel):
    file_id: str
    file_name: str
    status: str

class SearchResult(BaseModel):
    document_id: str
    text: str
    score: float
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    processing_time: str

@app.get("/v1/collections")
async def list_collections(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    filters: str = Query(default="{}"),
    sort: Optional[str] = Query(None, description="Format: field1,-field2,field3")
):
    offset = (page - 1) * per_page
    query = "SELECT data FROM collections"
    params = []

    filters_dict = json.loads(filters)
    if filters_dict:
        query += " WHERE " + " AND ".join(f"json_extract(data, '$.{k}') = ?" for k in filters_dict)
        params.extend(filters_dict.values())

    if sort:
        sort_fields = []
        for field in sort.split(','):
            if field.startswith('-'):
                sort_fields.append(f"json_extract(data, '$.{field[1:]}') DESC")
            else:
                sort_fields.append(f"json_extract(data, '$.{field}') ASC")
        query += " ORDER BY " + ", ".join(sort_fields)

    query += f" LIMIT ? OFFSET ?"
    params.extend([per_page, offset])

    with get_db() as db:
        results = [json.loads(row['data']) for row in db.execute(query, params)]
        total = db.execute("SELECT COUNT(*) FROM collections").fetchone()[0]

    return {"collections": results, "total": total}

@app.get("/v1/collections/{collection_id}")
async def get_collection(collection_id: str):
    with get_db() as db:
        result = db.execute("SELECT data FROM collections WHERE id = ?", (collection_id,)).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Collection not found")
    return json.loads(result['data'])

@app.post("/v1/collections", status_code=201)
async def create_collection(collection: CollectionCreate):
    collection_id = str(uuid.uuid4())
    data = collection.model_dump()
    data['id'] = collection_id
    data['created_at'] = datetime.now(timezone.utc).isoformat()

    with get_db() as db:
        db.execute("INSERT INTO collections (id, data) VALUES (?, ?)",
                   (collection_id, json.dumps(data)))

    return data

@app.patch("/v1/collections/{collection_id}")
async def update_collection(collection_id: str, update_data: CollectionUpdate):
    with get_db() as db:
        existing = db.execute("SELECT data FROM collections WHERE id = ?", (collection_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Collection not found")

        data = json.loads(existing['data'])
        data.update({k: v for k, v in update_data.model_dump().items() if v is not None})

        db.execute("UPDATE collections SET data = ? WHERE id = ?",
                   (json.dumps(data), collection_id))

    return data

@app.delete("/v1/collections/{collection_id}", status_code=204)
async def delete_collection(collection_id: str):
    with get_db() as db:
        result = db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Collection not found")
    return None

@app.post("/v1/collections/{collection_id}/documents", response_model=DocumentResponse, status_code=201)
async def add_document(
    collection_id: str,
    file: UploadFile = File(...),
    token: str = Depends(get_token)
):
    with get_db() as db:
        result = db.execute("SELECT data FROM collections WHERE id = ?", (collection_id,)).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Collection not found")
    embedding_model = json.loads(result['data'])['embedding_model']

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
        temp_file.write(await file.read())
        temp_file_path = temp_file.name

    try:
        loader = PyMuPDFLoader(temp_file_path)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=20)
        documents = text_splitter.split_documents(loader.load())
        for doc in documents:
            doc.metadata.update({"key": file.filename, "h1": f"{file.filename} p{doc.metadata['page'] + 1}"})

        Chroma.from_documents(
            documents,
            OpenAIEmbeddings(model=embedding_model),
            persist_directory=f".chromadb/{collection_id}",
            collection_name=collection_id,
        )

        return DocumentResponse(file_id=str(uuid.uuid4()), file_name=file.filename, status="processed")
    finally:
        os.unlink(temp_file_path)

@app.delete("/v1/collections/{collection_id}/documents/{file_id}", status_code=204)
async def delete_document(collection_id: str, file_id: str, token: str = Depends(get_token)):
    # Verify collection exists
    with get_db() as db:
        result = db.execute(
            "SELECT data FROM collections WHERE id = ?", (collection_id,)
        ).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Collection not found")

    try:
        shutil.rmtree(f".chromadb/{collection_id}", ignore_errors=True)
        return None  # 204 No Content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")


@app.get("/v1/collections/{collection_id}/search", response_model=SearchResponse)
async def vector_search(
    collection_id: str,
    q: str = Query(..., min_length=1),
    n: int = Query(10, ge=1, le=100),
    rerank_strategy: Optional[str] = None,
    similarity_threshold: float = Query(0.7, ge=0, le=1),
    fuzzy: bool = False,
    token: str = Depends(get_token)
):
    params = {
        "q": q,
        "n": n,
        "similarity_threshold": similarity_threshold,
        "fuzzy": fuzzy
    }
    if rerank_strategy:
        params["rerank_strategy"] = rerank_strategy
    return await forward_request(f"https://external-api.com/v1/collections/{collection_id}/search", "GET", token, params=params)

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    error_response = ErrorResponse(
        message=str(exc.detail),
        documentation_url=f"https://rag.straive.app/docs/{exc.status_code}",
        status_code=exc.status_code
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
