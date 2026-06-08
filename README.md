# RAG Law VN

Dự án RAG luật Việt Nam.

## Backend chat API

Da co san backend `/chat` de noi frontend vao model AI trong `rag/generation.py`.

Chay local:

```bash
cd api
pip install -r requirements.txt
fastapi dev main.py
```

## Frontend

Frontend React + TypeScript nằm trong thư mục `web/`. 

Chạy local:

```bash
cd ../web
npm install
npm run dev
```

Nếu đã có backend nhận câu hỏi, cấu hình biến môi trường:

```env
VITE_CHAT_API_URL=http://localhost:8000/chat
```

