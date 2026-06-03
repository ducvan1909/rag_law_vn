import gzip
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
EXPORT_PATH = SCRIPT_DIR / "vbpl_embed.jsonl.gz"
PARTIAL_PATH = SCRIPT_DIR / "vbpl_embed.jsonl.gz.partial"
COLLECTION_NAME = "vbpl_embed"
BATCH_SIZE = 128
METRIC = "cosine"


def getenv_int(name, default):
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc


def get_metric(collection):
    configuration = collection.configuration or {}
    hnsw_configuration = configuration.get("hnsw") or {}
    return hnsw_configuration.get("space") or (collection.metadata or {}).get("hnsw:space")


def get_dimension(collection):
    model = getattr(collection, "_model", None)
    return getattr(model, "dimension", None)


def to_json_value(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    return value


def write_json_line(output_file, value):
    json.dump(to_json_value(value), output_file, ensure_ascii=False, separators=(",", ":"))
    output_file.write("\n")


def main():
    load_dotenv(ROOT_DIR / ".env")
    host = os.getenv("CHROMA_HOST", "localhost")
    port = getenv_int("CHROMA_PORT", 8001)

    client = chromadb.HttpClient(host=host, port=port)
    client.heartbeat()
    collection = client.get_collection(COLLECTION_NAME)

    metric = get_metric(collection)
    if metric != METRIC:
        raise RuntimeError(
            f"Collection {COLLECTION_NAME!r} uses metric {metric!r}; expected {METRIC!r}."
        )

    source_count = collection.count()
    dimension = get_dimension(collection)
    manifest = {
        "type": "manifest",
        "format": "rag-law-vn-chroma-export",
        "format_version": 1,
        "collection": COLLECTION_NAME,
        "count": source_count,
        "dimension": dimension,
        "metric": METRIC,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    if PARTIAL_PATH.exists():
        PARTIAL_PATH.unlink()

    exported_count = 0
    print(f"Exporting {source_count} records from {COLLECTION_NAME!r}...")
    with gzip.open(PARTIAL_PATH, "wt", encoding="utf-8", newline="\n") as output_file:
        write_json_line(output_file, manifest)
        for offset in range(0, source_count, BATCH_SIZE):
            batch = collection.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas", "embeddings", "uris"],
            )
            record_count = len(batch["ids"])
            if record_count == 0:
                raise RuntimeError(f"Collection returned an empty batch at offset {offset}.")

            write_json_line(
                output_file,
                {
                    "type": "records",
                    "ids": batch["ids"],
                    "documents": batch["documents"],
                    "metadatas": batch["metadatas"],
                    "embeddings": batch["embeddings"],
                    "uris": batch["uris"],
                },
            )
            exported_count += record_count
            print(f"Exported {exported_count}/{source_count} records")

    if exported_count != source_count:
        raise RuntimeError(f"Exported {exported_count} records; expected {source_count}.")

    os.replace(PARTIAL_PATH, EXPORT_PATH)
    print(f"Export completed: {EXPORT_PATH}")


if __name__ == "__main__":
    main()
