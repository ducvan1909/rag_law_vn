import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from database.db_config import db
from database.mysql_model import VBPLUnit


DEFAULT_MODEL_NAME = "truro7/vn-law-embedding"
DEFAULT_COLLECTION_NAME = "vbpl_units"
DEFAULT_CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
DEFAULT_CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
DEFAULT_MAX_TOKENS = 600
DEFAULT_CHUNK_OVERLAP = 40
DEFAULT_EMBED_BATCH_SIZE = 32


def load_tokenizer(model_name, trust_remote_code=False):
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: transformers. Install with: "
            "python -m pip install -r rag/requirements.txt"
        ) from exc

    return AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=trust_remote_code,
    )


class EmbeddingModel:
    def __init__(self, model_name, tokenizer, device=None, trust_remote_code=False):
        self.model_name = model_name
        self.tokenizer = tokenizer
        self.device = device
        self.trust_remote_code = trust_remote_code
        self.backend = None
        self.model = None
        self.torch = None

        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer

            kwargs = {}
            if self.device:
                kwargs["device"] = self.device
            self.model = SentenceTransformer(self.model_name, **kwargs)
            self.backend = "sentence-transformers"
            return
        except ImportError:
            pass
        except Exception as exc:
            print(f"sentence-transformers backend unavailable: {exc}")
            print("falling back to transformers mean pooling")

        try:
            import torch
            from transformers import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "Missing embedding dependencies. Install sentence-transformers, "
                "or install transformers and torch."
            ) from exc

        self.torch = torch
        self.model = AutoModel.from_pretrained(
            self.model_name,
            trust_remote_code=self.trust_remote_code,
        )
        if self.device:
            self.model = self.model.to(self.device)
        self.model.eval()
        self.backend = "transformers"

    def encode(self, texts, batch_size, max_tokens):
        if self.backend == "sentence-transformers":
            return self.model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).tolist()

        return self._encode_with_transformers(texts, batch_size, max_tokens)

    def _encode_with_transformers(self, texts, batch_size, max_tokens):
        embeddings = []
        torch = self.torch

        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch_texts = texts[start : start + batch_size]
                encoded = self.tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=max_tokens,
                    return_tensors="pt",
                )
                if self.device:
                    encoded = {key: value.to(self.device) for key, value in encoded.items()}

                outputs = self.model(**encoded)
                token_embeddings = outputs.last_hidden_state
                attention_mask = encoded["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
                summed = (token_embeddings * attention_mask).sum(dim=1)
                counts = attention_mask.sum(dim=1).clamp(min=1e-9)
                batch_embeddings = summed / counts
                batch_embeddings = torch.nn.functional.normalize(batch_embeddings, p=2, dim=1)
                embeddings.extend(batch_embeddings.cpu().tolist())

        return embeddings


def normalize_text(value):
    if value is None:
        return ""
    return "\n".join(line.strip() for line in str(value).splitlines()).strip()


def token_count(tokenizer, text):
    if not text:
        return 0
    return len(tokenizer.encode(text, add_special_tokens=False))


def split_token_window(tokenizer, text, max_tokens, overlap_tokens):
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


def split_long_article(tokenizer, text, max_tokens=DEFAULT_MAX_TOKENS, overlap_tokens=DEFAULT_CHUNK_OVERLAP):
    text = normalize_text(text)
    if not text:
        return []
    if token_count(tokenizer, text) <= max_tokens:
        return [text]

    chunks = []
    current_parts = []

    for paragraph in [part.strip() for part in text.split("\n\n") if part.strip()]:
        if token_count(tokenizer, paragraph) > max_tokens:
            if current_parts:
                chunks.extend(split_token_window(tokenizer, "\n\n".join(current_parts), max_tokens, overlap_tokens))
                current_parts = []
            chunks.extend(split_token_window(tokenizer, paragraph, max_tokens, overlap_tokens))
            continue

        candidate_parts = current_parts + [paragraph]
        candidate = "\n\n".join(candidate_parts)
        if token_count(tokenizer, candidate) <= max_tokens:
            current_parts = candidate_parts
            continue

        if current_parts:
            chunks.extend(split_token_window(tokenizer, "\n\n".join(current_parts), max_tokens, overlap_tokens))
        current_parts = [paragraph]

    if current_parts:
        chunks.extend(split_token_window(tokenizer, "\n\n".join(current_parts), max_tokens, overlap_tokens))

    safe_chunks = []
    for chunk in chunks:
        if token_count(tokenizer, chunk) <= max_tokens:
            safe_chunks.append(chunk)
        else:
            safe_chunks.extend(split_token_window(tokenizer, chunk, max_tokens, overlap_tokens))

    return safe_chunks


def get_fk_id(row, field_name):
    raw_attr = f"{field_name}_id"
    if hasattr(row, raw_attr):
        return getattr(row, raw_attr)

    value = getattr(row, field_name)
    if hasattr(value, "get_id"):
        return value.get_id()
    return value


def safe_metadata_value(value):
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_metadata(unit, chunk_index, chunk_count, chunk_text, tokenizer, model_name):
    metadata = {
        "source_table": "vbpl_unit",
        "unit_id": unit.id,
        "document_id": get_fk_id(unit, "document_id"),
        "dieu_id": get_fk_id(unit, "dieu_id"),
        "dieu": unit.dieu,
        "chuong": unit.chuong,
        "demuc": unit.demuc,
        "chude": unit.chude,
        "ten_vbpl": unit.ten_vbpl,
        "char_start": unit.char_start if unit.char_start is not None else -1,
        "char_end": unit.char_end if unit.char_end is not None else -1,
        "status_name": unit.status_name,
        "chunk_index": chunk_index,
        "chunk_count": chunk_count,
        "token_count": token_count(tokenizer, chunk_text),
        "embedding_model": model_name,
    }
    return {key: safe_metadata_value(value) for key, value in metadata.items()}


def iter_vbpl_units(limit=None):
    query = (
        VBPLUnit.select()
        .where((VBPLUnit.content.is_null(False)) & (VBPLUnit.content != ""))
        .order_by(VBPLUnit.id)
    )
    if limit:
        query = query.limit(limit)

    for unit in query.iterator():
        yield unit


def get_chroma_collection(host, port, collection_name, reset=False):
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency: chromadb. Install with: "
            "python -m pip install -r rag/requirements.txt"
        ) from exc

    client = chromadb.HttpClient(host=host, port=port)
    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def flush_batch(collection, ids, documents, metadatas, embeddings):
    if not ids:
        return
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def index_vbpl_units(args):
    tokenizer = load_tokenizer(args.model_name, trust_remote_code=args.trust_remote_code)
    model = EmbeddingModel(
        args.model_name,
        tokenizer=tokenizer,
        device=args.device,
        trust_remote_code=args.trust_remote_code,
    )
    collection = get_chroma_collection(
        host=args.chroma_host,
        port=args.chroma_port,
        collection_name=args.collection_name,
        reset=args.reset,
    )

    ids = []
    documents = []
    metadatas = []
    indexed_chunks = 0
    indexed_units = 0

    db.connect(reuse_if_open=True)
    try:
        for unit in iter_vbpl_units(limit=args.limit):
            chunks = split_long_article(
                tokenizer=tokenizer,
                text=unit.content,
                max_tokens=args.max_tokens,
                overlap_tokens=args.chunk_overlap,
            )
            if not chunks:
                continue

            indexed_units += 1
            chunk_count = len(chunks)
            for chunk_index, chunk in enumerate(chunks):
                ids.append(f"vbpl_unit:{unit.id}:chunk:{chunk_index}")
                documents.append(chunk)
                metadatas.append(
                    build_metadata(unit, chunk_index, chunk_count, chunk, tokenizer, args.model_name)
                )

                if len(ids) >= args.embed_batch_size:
                    embeddings = model.encode(
                        documents,
                        batch_size=args.embed_batch_size,
                        max_tokens=args.max_tokens,
                    )
                    flush_batch(collection, ids, documents, metadatas, embeddings)
                    indexed_chunks += len(ids)
                    print(f"indexed chunks: {indexed_chunks}")
                    ids, documents, metadatas = [], [], []

        if ids:
            embeddings = model.encode(
                documents,
                batch_size=args.embed_batch_size,
                max_tokens=args.max_tokens,
            )
            flush_batch(collection, ids, documents, metadatas, embeddings)
            indexed_chunks += len(ids)

    finally:
        if not db.is_closed():
            db.close()

    print(f"indexed units: {indexed_units}")
    print(f"indexed chunks: {indexed_chunks}")
    print(f"collection: {args.collection_name}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Index VBPLUnit rows into ChromaDB with tokenizer-aware chunking."
    )
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--collection-name", default=DEFAULT_COLLECTION_NAME)
    parser.add_argument("--chroma-host", default=DEFAULT_CHROMA_HOST)
    parser.add_argument("--chroma-port", type=int, default=DEFAULT_CHROMA_PORT)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--embed-batch-size", type=int, default=DEFAULT_EMBED_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.max_tokens <= 0:
        raise ValueError("--max-tokens must be positive")
    if args.chunk_overlap < 0:
        raise ValueError("--chunk-overlap cannot be negative")
    if args.chunk_overlap >= args.max_tokens:
        raise ValueError("--chunk-overlap must be smaller than --max-tokens")
    if args.embed_batch_size <= 0:
        raise ValueError("--embed-batch-size must be positive")

    index_vbpl_units(args)


if __name__ == "__main__":
    main()
