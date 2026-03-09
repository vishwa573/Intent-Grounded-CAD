import os
import chromadb
from sentence_transformers import SentenceTransformer

COLLECTION_NAME = "build123d_docs"
EMBED_MODEL = "all-MiniLM-L6-v2"
CHROMA_DIR = "chroma_db"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CHROMA_PATH = os.path.join(PROJECT_ROOT, CHROMA_DIR)
CHROMA_CLIENT = chromadb.PersistentClient(path=CHROMA_PATH)
EMBEDDING_MODEL = SentenceTransformer(EMBED_MODEL)

def _get_docs_dir():
    docs_dir = os.path.join(PROJECT_ROOT, "build123d-docs", "docs")
    if not os.path.isdir(docs_dir):
        docs_dir = os.path.join(PROJECT_ROOT, "build123d-docs")
    return docs_dir

def _iter_doc_files(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".rst") or filename.endswith(".md"):
                yield os.path.join(dirpath, filename)

def _chunk_text(text, chunk_size=500):
    words = text.split()
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        if chunk_words:
            yield " ".join(chunk_words)

def build_vector_db():
    docs_dir = _get_docs_dir()
    if not os.path.isdir(docs_dir):
        raise FileNotFoundError(f"Docs directory not found: {docs_dir}")

    try:
        CHROMA_CLIENT.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = CHROMA_CLIENT.get_or_create_collection(name=COLLECTION_NAME)

    documents = []
    metadatas = []
    ids = []
    doc_index = 0

    for file_path in _iter_doc_files(docs_dir):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            continue
        for chunk in _chunk_text(text):
            documents.append(chunk)
            metadatas.append({"source": file_path})
            ids.append(f"doc_{doc_index}")
            doc_index += 1

    if not documents:
        return 0

    embeddings = EMBEDDING_MODEL.encode(documents, show_progress_bar=False).tolist()
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return len(documents)   

def retrieve_context(query, k=3):
    try:
        collection = CHROMA_CLIENT.get_collection(name=COLLECTION_NAME)
        query_embedding = EMBEDDING_MODEL.encode([query], show_progress_bar=False).tolist()
        results = collection.query(query_embeddings=query_embedding, n_results=k)
        documents = results.get("documents", [])
        if documents and len(documents) > 0:
            return documents[0]
        return []
    except Exception:
        return []
