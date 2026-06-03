import gzip
import json
import os
from pathlib import Path

import chromadb
from chromadb.errors import NotFoundError
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
IMPORT_PATH = SCRIPT_DIR / "vbpl_embed.jsonl.gz"
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


def read_json_line(input_file, line_number):
    line = input_file.readline()
    if not line:
        raise RuntimeError(f"Unexpected end of file at line {line_number}.")

    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON at line {line_number}.") from exc


def validate_manifest(manifest):
    expected_values = {
        "type": "manifest",
        "format": "rag-law-vn-chroma-export",
        "format_version": 1,
        "collection": COLLECTION_NAME,
        "metric": METRIC,
    }
    for key, expected_value in expected_values.items():
        actual_value = manifest.get(key)
        if actual_value != expected_value:
            raise RuntimeError(
                f"Manifest field {key!r} is {actual_value!r}; expected {expected_value!r}."
            )

    count = manifest.get("count")
    if not isinstance(count, int) or count < 0:
        raise RuntimeError("Manifest field 'count' must be a non-negative integer.")

    dimension = manifest.get("dimension")
    if count > 0 and (not isinstance(dimension, int) or dimension <= 0):
        raise RuntimeError("Manifest field 'dimension' must be a positive integer.")


def validate_batch(batch, line_number, dimension):
    if batch.get("type") != "records":
        raise RuntimeError(f"Invalid record type at line {line_number}.")

    ids = batch.get("ids")
    embeddings = batch.get("embeddings")
    if not isinstance(ids, list) or not ids:
        raise RuntimeError(f"Batch at line {line_number} must contain at least one ID.")
    if not isinstance(embeddings, list) or len(embeddings) != len(ids):
        raise RuntimeError(f"Embedding count does not match ID count at line {line_number}.")
    if len(ids) > BATCH_SIZE:
        raise RuntimeError(f"Batch at line {line_number} exceeds the supported batch size.")

    for key in ("documents", "metadatas", "uris"):
        values = batch.get(key)
        if values is not None and (not isinstance(values, list) or len(values) != len(ids)):
            raise RuntimeError(f"{key!r} count does not match ID count at line {line_number}.")

    for embedding in embeddings:
        if not isinstance(embedding, list) or len(embedding) != dimension:
            raise RuntimeError(f"Invalid embedding dimension at line {line_number}.")


def get_or_create_collection(client):
    try:
        collection = client.get_collection(COLLECTION_NAME)
        print(f"Using existing collection {COLLECTION_NAME!r}.")
        return collection
    except NotFoundError:
        print(f"Creating collection {COLLECTION_NAME!r} with metric {METRIC!r}.")
        return client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": METRIC},
            configuration={"hnsw": {"space": METRIC}},
        )


def validate_collection(collection, expected_dimension):
    metric = get_metric(collection)
    if metric != METRIC:
        raise RuntimeError(
            f"Collection {COLLECTION_NAME!r} uses metric {metric!r}; expected {METRIC!r}."
        )

    dimension = get_dimension(collection)
    if dimension is not None and expected_dimension is not None and dimension != expected_dimension:
        raise RuntimeError(
            f"Collection {COLLECTION_NAME!r} uses dimension {dimension}; "
            f"expected {expected_dimension}."
        )


def main():
    load_dotenv(ROOT_DIR / ".env")
    host = os.getenv("CHROMA_HOST", "localhost")
    port = getenv_int("CHROMA_PORT", 8001)

    if not IMPORT_PATH.is_file():
        raise RuntimeError(f"Import file does not exist: {IMPORT_PATH}")

    client = chromadb.HttpClient(host=host, port=port)
    client.heartbeat()

    imported_count = 0
    with gzip.open(IMPORT_PATH, "rt", encoding="utf-8") as input_file:
        manifest = read_json_line(input_file, 1)
        validate_manifest(manifest)
        source_count = manifest["count"]
        expected_dimension = manifest["dimension"]

        collection = get_or_create_collection(client)
        validate_collection(collection, expected_dimension)
        count_before = collection.count()

        print(f"Importing {source_count} records into {COLLECTION_NAME!r}...")
        for line_number, line in enumerate(input_file, start=2):
            try:
                batch = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Invalid JSON at line {line_number}.") from exc

            validate_batch(batch, line_number, expected_dimension)
            collection.add(
                ids=batch["ids"],
                documents=batch.get("documents"),
                metadatas=batch.get("metadatas"),
                embeddings=batch["embeddings"],
                uris=batch.get("uris"),
            )
            imported_count += len(batch["ids"])
            print(f"Processed {imported_count}/{source_count} records")

    if imported_count != source_count:
        raise RuntimeError(f"Processed {imported_count} records; expected {source_count}.")

    count_after = collection.count()
    print(f"Import completed: collection count {count_before} -> {count_after}")
    print("Existing record IDs were kept unchanged.")


if __name__ == "__main__":
    main()
