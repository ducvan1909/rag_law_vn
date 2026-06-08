import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
from sentence_transformers import SentenceTransformer

import chromadb
from database.db_config import db
from database.mysql_model import VBPLUnit

model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
hf_token = os.getenv("HF_TOKEN")
collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embed")
chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))
embedding_device = os.getenv("EMBEDDING_DEVICE", "cpu")
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "128"))
MAX_TOKENS = 500
CHUNK_OVERLAP = 50

def resolve_device(device_name):
    requested = (device_name or "auto").strip().lower()

    try:
        import torch
    except ImportError:
        if requested != "auto":
            print("torch is unavailable, falling back to cpu")
        return "cpu"

    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    if requested.startswith("cuda") and not torch.cuda.is_available():
        print(f"requested device '{device_name}' is unavailable, falling back to cpu")
        return "cpu"

    if requested == "mps":
        has_mps = hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
        if not has_mps:
            print("requested device 'mps' is unavailable, falling back to cpu")
            return "cpu"

    return device_name

def iter_data(limit=None):
    if limit is None:
        query = (
            VBPLUnit
            .select(VBPLUnit.id, VBPLUnit.dieu, VBPLUnit.chude, VBPLUnit.chuong,
                    VBPLUnit.demuc, VBPLUnit.content, VBPLUnit.ten_vbpl, VBPLUnit.status_name)
            .where(~(VBPLUnit.status_name.contains("Hết hiệu lực toàn bộ")))
            .dicts()
        )
    else:
        query = (
            VBPLUnit
            .select(VBPLUnit.id, VBPLUnit.dieu, VBPLUnit.chude, VBPLUnit.chuong,
                    VBPLUnit.demuc, VBPLUnit.content, VBPLUnit.ten_vbpl, VBPLUnit.status_name)
            .where(~(VBPLUnit.status_name.contains("Hết hiệu lực toàn bộ")))
            .dicts()
            .limit(limit)
        )
    for row in query.iterator():
        yield row

def split_token_window(tokenizer, text, max_tokens=MAX_TOKENS-100, overlap_tokens=CHUNK_OVERLAP):
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return [(text, len(token_ids))]

    chunks = []
    start = 0
    step_back = min(overlap_tokens, max_tokens - 1)

    while start < len(token_ids):
        end = min(start + max_tokens, len(token_ids))
        chunk_token_ids = token_ids[start:end]
        chunk = tokenizer.decode(
            chunk_token_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        ).strip()
        if chunk:
            chunks.append((chunk, len(chunk_token_ids)))
        if end == len(token_ids):
            break
        start = end - step_back

    return chunks

def build_retrieval_text(unit, chunk):
    documents = [
        f"Chủ đề: {unit['chude']}",
        f"Đề mục: {unit['demuc']}",
        f"Chương: {unit['chuong']}",
        f"Điều: {unit['dieu']}",
        f"Văn bản: {unit['ten_vbpl']}",
        f"Nội dung: {chunk}",
    ]
    return "\n".join(document for document in documents if document.split(": ", 1)[-1])

def build_metadata(unit, chunk_token_count):
    metadata = {
        "unit_id": unit["id"],
        "dieu": unit["dieu"],
        "chuong": unit["chuong"],
        "demuc": unit["demuc"],
        "chude": unit["chude"],
        "ten_vbpl": unit["ten_vbpl"],
        "status_name": unit["status_name"],
        "token_count": chunk_token_count,
    }
    return metadata

def index_units(embedding_model, units, collection):
    tokenizer = embedding_model.tokenizer
    ids = []
    metadatas = []
    documents = []
    retrieval_documents = []
    indexed_units = 0
    indexed_chunks = 0
    for unit in units:
        chunks = split_token_window(tokenizer, unit["content"])
        for index_chunk, (chunk, chunk_token_count) in enumerate(chunks):
            metadatas.append(build_metadata(unit, chunk_token_count))
            ids.append(f"Unit {indexed_units} - Chunk {index_chunk}")
            documents.append(chunk)
            retrieval_documents.append(build_retrieval_text(unit, chunk))
            if len(ids) >= EMBED_BATCH_SIZE:
                embeddings = embedding_model.encode(retrieval_documents, batch_size=EMBED_BATCH_SIZE)
                upsert_batch(collection, ids, documents, embeddings, metadatas)
                indexed_chunks += len(ids)
                print(f"indexed units: {indexed_units + 1}, indexed chunks: {indexed_chunks}")
                ids = []
                metadatas = []
                documents = []
                retrieval_documents = []
        indexed_units += 1
    if ids:
        embeddings = embedding_model.encode(retrieval_documents, batch_size=EMBED_BATCH_SIZE)
        upsert_batch(collection, ids, documents, embeddings, metadatas)
        indexed_chunks += len(ids)
    print(f"indexed units: {indexed_units}, indexed chunks: {indexed_chunks}")

def upsert_batch(collection, ids, documents, embeddings, metadatas):
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )

def build_rerank_text(result):
    metadata = result["metadata"]

    return "\n".join([
        f"Văn bản: {metadata['ten_vbpl']}",
        f"Chủ đề: {metadata['chude']}",
        f"Đề mục: {metadata['demuc']}",
        f"Chương: {metadata['chuong']}",
        f"Điều: {metadata['dieu']}",
        f"Nội dung: {result['document']}",
    ])

if __name__ == "__main__":
    started_at = time.perf_counter()
    try:
        chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        try:
            chroma_client.delete_collection(collection_name)
        except Exception as e:
            print(f"{e}")

        collection = chroma_client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
        device = resolve_device(embedding_device)
        print(f"Using embedding device: {device}")
        embedding_model = SentenceTransformer(model_name, token=hf_token, device=device)
        db.connect(reuse_if_open=True)
        units = iter_data()
        index_units(embedding_model, units, collection)

        print("Success")
    finally:
        if not db.is_closed():
            db.close()
        elapsed_seconds = time.perf_counter() - started_at
        print(f"Total runtime: {elapsed_seconds:.2f}s")
