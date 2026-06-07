# Web Frontend

Frontend React + TypeScript tối giản cho `RAG Law VN`.

Lưu ý: repo này hiện đang cấu hình để chạy với Node `v19.x`. Nếu muốn dùng Vite 7 trở lên, hãy nâng Node lên `20.19+` hoặc `22.12+`.


## Backend chat API
```bash
cd api
pip install -r requirements.txt
fastapi dev main.py


```
## Chạy local
```bash
cd web
npm install
npm run dev
```

## Kết nối backend

Đặt biến môi trường `VITE_CHAT_API_URL` để trỏ tới endpoint nhận câu hỏi:

```env
VITE_CHAT_API_URL=http://localhost:8000/chat
```







Endpoint:

- `POST /chat` voi JSON `{ "question": "..." }`
- `GET /health` de kiem tra server
