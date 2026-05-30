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
collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embeds")
chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))
embedding_device = os.getenv("EMBEDDING_DEVICE", "auto")
MAX_TOKENS = 500
CHUNK_OVERLAP = 10
BATCH_SIZE = 128

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

def get_tokens_length(tokenizer, corpus):
    tokens = tokenizer.encode(corpus, add_special_tokens=False)
    return len(tokens)

def split_token_window(tokenizer, text, max_tokens=MAX_TOKENS, overlap_tokens=CHUNK_OVERLAP):
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= max_tokens:
        return [text]

    chunks = []
    start = 0
    step_back = min(overlap_tokens, max_tokens - 1)

    while start < len(token_ids):
        end = min(start + max_tokens, len(token_ids))
        chunk = tokenizer.decode(
            token_ids[start:end],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
        ).strip()
        if chunk:
            chunks.append(chunk)
        if end == len(token_ids):
            break
        start = end - step_back

    return chunks

def build_metadata(unit, chunk_text, tokenizer):
    metadata = {
        "unit_id": unit["id"],
        "dieu": unit["dieu"],
        "chuong": unit["chuong"],
        "demuc": unit["demuc"],
        "chude": unit["chude"],
        "ten_vbpl": unit["ten_vbpl"],
        "status_name": unit["status_name"],
        "token_count": get_tokens_length(tokenizer, chunk_text)
    }
    return metadata

def index_units(embedding_model, units, collection):
    tokenizer = embedding_model.tokenizer
    ids = []
    metadatas = []
    documents = []
    index_units = 0
    for unit in units:
        chunks = split_token_window(tokenizer, unit["content"])
        index_chunk = 0
        for chunk in chunks:
            metadatas.append(build_metadata(unit, chunk, tokenizer))
            ids.append(f"Unit {index_units} - Chunk {index_chunk}")
            documents.append(chunk)
            index_chunk += 1
        index_units += 1
        if len(ids) >= BATCH_SIZE:
            embeddings = embedding_model.encode(documents, batch_size=BATCH_SIZE)
            upsert_batch(collection, ids, documents, embeddings, metadatas)
            print(index_units)
            ids = []
            metadatas = []
            documents = []
    if len(ids) != 0:
        embeddings = embedding_model.encode(documents, batch_size=BATCH_SIZE)
        upsert_batch(collection, ids, documents, embeddings, metadatas)
        print(index_units)

def upsert_batch(collection, ids, documents, embeddings, metadatas):
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )

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
