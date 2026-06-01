import chromadb
import os
from sentence_transformers import SentenceTransformer
from indexing import resolve_device

model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
hf_token = os.getenv("HF_TOKEN")
embedding_device = os.getenv("EMBEDDING_DEVICE", "auto")
collection_name = os.getenv("CHROMA_COLLECTION", "vbpl_embeds")
chroma_host = os.getenv("CHROMA_HOST", "localhost")
chroma_port = int(os.getenv("CHROMA_PORT", "8001"))



def retrieve(query, embedding_model, collection, n_results=5):
    query_embeddings = embedding_model.encode(query)
    res = collection.query(query_embeddings=query_embeddings, n_results=5)
    return res

if __name__ == "__main__":
    embedding_model = SentenceTransformer(model_name)
    chroma_client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    collection = chroma_client.get_collection(collection_name)

    results = retrieve(["dân sự"], embedding_model, collection)
    for result in results["documents"][0]:
        print(result)