import os
import re
from pathlib import Path
from dotenv import load_dotenv

import numpy as np

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import chromadb

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

embedding_model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
embedding_model = SentenceTransformer(embedding_model_name)
hf_token = os.getenv("HF_TOKEN")
embedding_device = os.getenv("EMBEDDING_DEVICE", "auto")

rerank_model_name = os.getenv("RERANK_MODEL")
tokenizer = AutoTokenizer.from_pretrained(rerank_model_name)
rerank_model = AutoModelForSequenceClassification.from_pretrained(rerank_model_name)
rerank_model.eval()
MAX_LENGTH = 512

chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))
chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embed")
collection = chroma_client.get_collection(collection_name)

PASSAGE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?;])\s+|\n+")

def chroma_results_to_list(results, batch_index=0):
    rows = []
    documents = results.get("documents", [[]])[batch_index]

    for i in range(len(documents)):
        row = {
            "index": i,
            "id": results.get("ids", [[]])[batch_index][i],
            "document": results.get("documents", [[]])[batch_index][i],
            "metadata": results.get("metadatas", [[]])[batch_index][i],
        }

        if "distances" in results and results["distances"]:
            row["distance"] = results["distances"][batch_index][i]

        rows.append(row)

    return rows

def retrieve(query, embedding_model=embedding_model, collection=collection, n_results=5):
    query_embeddings = embedding_model.encode(query)
    raw_results = collection.query(query_embeddings=query_embeddings, n_results=n_results*10)
    raw_results = chroma_results_to_list(raw_results, batch_index=0)
    reranked_results = rerank(query, raw_results)
    # res = extract(query, res)
    return reranked_results[:n_results]

def extract(query, results, embedding_model=embedding_model, passages_per_document=2, context_window=1):
    """Keep only the most relevant passages and their neighbors in each retrieved chunk."""
    if passages_per_document < 1:
        raise ValueError("passages_per_document must be greater than 0")
    if context_window < 0:
        raise ValueError("context_window must be greater than or equal to 0")

    document_batches = results.get("documents")
    if not query.strip() or not document_batches:
        return results

    compressed_batches = []
    for documents in document_batches:
        compressed_documents = []
        for document in documents:
            passages = [
                passage.strip()
                for passage in PASSAGE_BOUNDARY_PATTERN.split(document)
                if passage.strip()
            ]
            if len(passages) <= passages_per_document:
                compressed_documents.append(document)
                continue

            embeddings = embedding_model.encode(
                [query, *passages],
                normalize_embeddings=True,
            )
            query_embedding = np.asarray(embeddings[0])
            passage_embeddings = np.asarray(embeddings[1:])
            scores = passage_embeddings @ query_embedding
            top_indexes = np.argsort(scores)[-passages_per_document:]

            selected_indexes = set()
            for index in top_indexes:
                start = max(0, index - context_window)
                end = min(len(passages), index + context_window + 1)
                selected_indexes.update(range(start, end))

            compressed_documents.append(
                " ".join(passages[index] for index in sorted(selected_indexes))
            )
        compressed_batches.append(compressed_documents)

    compressed_results = dict(results)
    compressed_results["documents"] = compressed_batches
    return compressed_results

def rerank(query, results):
    if not results:
        return results

    with torch.no_grad():
        pairs = [[query, result["document"]] for result in results]
        inputs = tokenizer(pairs, padding=True, truncation='only_second', return_tensors='pt', max_length=MAX_LENGTH)
        scores = rerank_model(**inputs, return_dict=True).logits.view(-1, ).float().tolist()

    for result, score in zip(results, scores):
        result["rerank_score"] = score

    return sorted(results, key=lambda result: result["rerank_score"], reverse=True)

if __name__ == "__main__":
    query = ""
    while query != "exit":
        query = input("Enter query: ")
        if query == exit:
            break
        results = retrieve(query, n_results=5)
        for result in results:
            print(result["document"])
            print("___________________")
