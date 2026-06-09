### Nếu muốn xóa ChromaDB nhanh

```
cd E:\Git\rag_law_vn

docker compose stop chromadb
docker compose rm -f chromadb
docker volume rm law-chroma-data
docker compose up -d chromadb
```