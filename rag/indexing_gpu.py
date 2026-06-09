import gc
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import chromadb
import numpy as np
import torch
from chromadb.errors import NotFoundError
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

load_dotenv(ROOT_DIR / ".env")

from database.db_config import db
from rag.indexing import (
    build_metadata,
    build_retrieval_text,
    iter_data,
    split_token_window,
)

model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
hf_token = os.getenv("HF_TOKEN")
collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embed")
chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))
EMBED_BATCH_SIZE = int(os.getenv("GPU_EMBED_BATCH_SIZE", "64"))
MIN_BATCH_SIZE = 4


def prepare_collection():
    if not collection_name:
        raise RuntimeError("CHROMA_COLLECTION must not be empty.")

    client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    try:
        client.delete_collection(collection_name)
    except NotFoundError:
        pass

    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    if collection.count() != 0:
        raise RuntimeError(f"Collection {collection_name!r} was not cleared.")
    return collection


def encode_gpu(embedding_model, documents, batch_size):
    while True:
        embedding_tensor = None
        try:
            with torch.inference_mode():
                embedding_tensor = embedding_model.encode(
                    documents,
                    batch_size=batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=False,
                    convert_to_tensor=True,
                )
            embeddings = np.asarray(
                embedding_tensor.detach()
                .to(device="cpu", dtype=torch.float32)
                .numpy(),
                dtype=np.float32,
            )
            del embedding_tensor
            return embeddings, batch_size
        except torch.cuda.OutOfMemoryError as exc:
            if batch_size <= MIN_BATCH_SIZE:
                raise RuntimeError(
                    f"CUDA OOM at minimum batch size {MIN_BATCH_SIZE}."
                ) from exc

            del embedding_tensor
            next_batch_size = max(MIN_BATCH_SIZE, batch_size // 2)
            print(
                f"CUDA OOM at batch size {batch_size}; "
                f"retrying with batch size {next_batch_size}."
            )
            batch_size = next_batch_size
            gc.collect()
            torch.cuda.empty_cache()


def upsert_batch(collection, ids, documents, embeddings, metadatas):
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def index_units(embedding_model, units, collection):
    tokenizer = embedding_model.tokenizer
    batch_size = EMBED_BATCH_SIZE
    ids = []
    metadatas = []
    documents = []
    retrieval_documents = []
    indexed_units = 0
    indexed_chunks = 0
    pending_upsert = None

    with ThreadPoolExecutor(max_workers=1) as writer:
        for unit in units:
            chunks = split_token_window(tokenizer, unit["content"])
            for index_chunk, (chunk, chunk_token_count) in enumerate(chunks):
                ids.append(f"Unit {indexed_units} - Chunk {index_chunk}")
                documents.append(chunk)
                metadatas.append(build_metadata(unit, chunk_token_count))
                retrieval_documents.append(build_retrieval_text(unit, chunk))

                if len(ids) >= batch_size:
                    embeddings, batch_size = encode_gpu(
                        embedding_model,
                        retrieval_documents,
                        batch_size,
                    )
                    if pending_upsert is not None:
                        pending_upsert.result()
                    pending_upsert = writer.submit(
                        upsert_batch,
                        collection,
                        ids,
                        documents,
                        embeddings,
                        metadatas,
                    )
                    indexed_chunks += len(ids)
                    print(
                        f"indexed units: {indexed_units + 1}, "
                        f"queued chunks: {indexed_chunks}, "
                        f"GPU batch size: {batch_size}"
                    )
                    ids = []
                    metadatas = []
                    documents = []
                    retrieval_documents = []
            indexed_units += 1

        if ids:
            embeddings, batch_size = encode_gpu(
                embedding_model,
                retrieval_documents,
                batch_size,
            )
            if pending_upsert is not None:
                pending_upsert.result()
            pending_upsert = writer.submit(
                upsert_batch,
                collection,
                ids,
                documents,
                embeddings,
                metadatas,
            )
            indexed_chunks += len(ids)

        if pending_upsert is not None:
            pending_upsert.result()

    print(f"indexed units: {indexed_units}, indexed chunks: {indexed_chunks}")
    return batch_size


if __name__ == "__main__":
    started_at = time.perf_counter()
    final_batch_size = EMBED_BATCH_SIZE
    try:
        if EMBED_BATCH_SIZE < MIN_BATCH_SIZE:
            raise RuntimeError(
                f"GPU_EMBED_BATCH_SIZE must be at least {MIN_BATCH_SIZE}."
            )
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; GPU indexing cannot run.")

        collection = prepare_collection()
        print(f"Cleared collection: {collection_name}")

        embedding_model = SentenceTransformer(
            model_name,
            token=hf_token,
            device="cuda",
            model_kwargs={"torch_dtype": torch.float16},
        )
        embedding_model.half()
        embedding_model.eval()
        torch.cuda.reset_peak_memory_stats()

        print("Using embedding device: cuda")
        print("Using embedding dtype: float16")
        print(f"Initial GPU batch size: {EMBED_BATCH_SIZE}")

        db.connect(reuse_if_open=True)
        final_batch_size = index_units(embedding_model, iter_data(), collection)
        print("Success")
    finally:
        if not db.is_closed():
            db.close()
        peak_vram = (
            torch.cuda.max_memory_allocated() / (1024 ** 3)
            if torch.cuda.is_available()
            else 0
        )
        print(f"Final GPU batch size: {final_batch_size}")
        print(f"Peak allocated VRAM: {peak_vram:.2f} GiB")
        print(f"Total runtime: {time.perf_counter() - started_at:.2f}s")
