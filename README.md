# RAG Law VN

Dự án RAG luật Việt Nam.

## Frontend

Frontend React + TypeScript nằm trong thư mục `web/`.

Nếu bạn đang dùng Node `v19.x` như máy hiện tại, cần cài lại dependencies sau khi tôi đã hạ Vite xuống bản tương thích. Nếu muốn giữ Vite mới hơn, hãy nâng Node lên `20.19+` hoặc `22.12+`.

Chạy local:

```bash
cd web
npm install
npm run dev
```

Nếu đã có backend nhận câu hỏi, cấu hình biến môi trường:

```env
VITE_CHAT_API_URL=http://localhost:8000/chat
```
