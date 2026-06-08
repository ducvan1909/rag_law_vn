import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
import chromadb

from database.mysql_model import PDChuDe
from database.db_config import db

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

embedding_model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
embedding_device = os.getenv("EMBEDDING_DEVICE", "auto")
hf_token = os.getenv("HF_TOKEN")
rerank_model_name = os.getenv("RERANK_MODEL")
rerank_device = torch.device("cpu")
classify_model_name = os.getenv("CLASSIFY_MODEL")
MAX_LENGTH = 700

chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))

collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embed")


PASSAGE_BOUNDARY_PATTERN = re.compile(r"(?<=[.!?;])\s+|\n+")


class RetrievalResources:
    def __init__(self):
        self.embedding_model = SentenceTransformer(embedding_model_name)
        self.rerank_tokenizer = AutoTokenizer.from_pretrained(rerank_model_name)
        self.rerank_model = (AutoModelForSequenceClassification.from_pretrained(rerank_model_name))
        self.rerank_model.to(rerank_device)
        self.rerank_model.eval()
        self.classify_model = pipeline("zero-shot-classification", model=classify_model_name)
        chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self.collection = chroma_client.get_collection(collection_name)
        self.topics = [row[0] for row in PDChuDe.select(PDChuDe.ten).tuples()]
def load_retrieval_resources():
    return RetrievalResources()

#Chuyển kết quả truy vấn ChromaDB từ dict chứa các list sang list chứa các dict để tiện xử lý
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

def retrieve(query, resources, n_results=5, timings=None):
    embedding_started_at = time.perf_counter()
    query_embeddings = resources.embedding_model.encode(query)
    embedding_finished_at = time.perf_counter()

    #Retrieve raw result from chromadb
    raw_results = resources.collection.query(
        query_embeddings=query_embeddings,
        n_results=n_results * 4,
    )
    chroma_finished_at = time.perf_counter()

    raw_results = chroma_results_to_list(raw_results, batch_index=0)

    rerank_started_at = time.perf_counter()
    reranked_results = rerank(
        query,
        raw_results,
        resources.rerank_tokenizer,
        resources.rerank_model,
    )
    rerank_finished_at = time.perf_counter()

    #Đếm thời gian embed, truy vấn chromadb và rerank
    if timings is not None:
        timings.update(
            {
                "embedding_ms": round(
                    (embedding_finished_at - embedding_started_at) * 1000,
                    2,
                ),
                "chroma_ms": round(
                    (chroma_finished_at - embedding_finished_at) * 1000,
                    2,
                ),
                "rerank_ms": round(
                    (rerank_finished_at - rerank_started_at) * 1000,
                    2,
                ),
                "retrieval_ms": round(
                    (rerank_finished_at - embedding_started_at) * 1000,
                    2,
                ),
                "candidate_count": len(raw_results),
                "result_count": min(n_results, len(reranked_results)),
            }
        )

    return reranked_results


#Rerank các kết quả truy vấn từ chromadb
def rerank(query, results, tokenizer, rerank_model, batch_size=10):
    if not results:
        return results
    if batch_size <= 0:
        raise ValueError("Invalid batch size")

    with torch.no_grad():
        scores = []
        for start in range(0, len(results), batch_size):
            pairs = [
                [query, result["document"]] for result in results[start:start + batch_size]
            ]
            inputs = tokenizer(
                pairs,
                padding=True,
                truncation="only_second",
                return_tensors="pt",
                max_length=MAX_LENGTH,
            )
            inputs = {
                key: value.to(rerank_device)
                for key, value in inputs.items()
            }
            batch_scores = rerank_model(
                **inputs,
                return_dict=True,
            ).logits.view(-1).float().tolist()
            scores.extend(batch_scores)

    for result, score in zip(results, scores):
        result["rerank_score"] = score

    return sorted(results, key=lambda result: result["rerank_score"], reverse=True)

def classify(query, topics, classify_model):
    output = classify_model(query, topics, hypothesis_template="Câu hỏi pháp luật này thuộc lĩnh vực {}.", multi_label=True)
    scores = [{topic: score} for topic, score in zip(output["labels"], output["scores"])]
    return scores

if __name__ == "__main__":
    db.connect(reuse_if_open=True)
    resources = RetrievalResources()
    query = ""
    while query != "exit":
        query = input("Enter query: ")
        if query == "exit":
            break
        labels = classify(query, resources.topics, resources.classify_model)
        i = 0
        for label in labels:
            i += 1
            print(i, label)
        results = retrieve(query, resources=resources, n_results=5)
        for result in results:
            print(f'{result["document"]}\n{result["rerank_score"]}')
            labels = classify(result["document"], resources.topics, resources.classify_model)
            i = 0
            for label in labels:
                i += 1
                print(i, label)
            print("___________________")

    db.close()