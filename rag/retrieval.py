import chromadb
import os
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
hf_token = os.getenv("HF_TOKEN")
embedding_device = os.getenv("EMBEDDING_DEVICE", "auto")
collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embed")
chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))
embedding_model = SentenceTransformer(model_name)
chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
collection = chroma_client.get_collection(collection_name)

def retrieve(query, embedding_model=embedding_model, collection=collection, n_results=5):
    query_embeddings = embedding_model.encode(query)
    res = collection.query(query_embeddings=query_embeddings, n_results=n_results)
    res = rerank(res)
    return res

def rerank(results):
    #Rerank .......
    return results

if __name__ == "__main__":
    print(retrieve(query="tổ chức sử dụng ma túy"))
