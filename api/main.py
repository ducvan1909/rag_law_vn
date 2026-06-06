from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag.generation import generate_answer, load_generation_model
from rag.retrieval import load_retrieval_resources

ROOT_DIR = Path(__file__).resolve().parent.parent


class ChatRequest(BaseModel):
    question: str


class ChatResponse(BaseModel):
    answer: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.generation_model = load_generation_model()
    app.state.retrieval_resources = load_retrieval_resources()

    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    question = request.question.strip()
    if question == "":
        raise HTTPException(status_code=400, detail="Question is required")
    try:
        answer = generate_answer(
            app.state.generation_model,
            question,
            retrieval_resources=app.state.retrieval_resources,
        )
        return ChatResponse(answer=answer)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
