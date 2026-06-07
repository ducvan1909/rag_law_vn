import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from rag.retrieval import RetrievalResources, retrieve

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

DEFAULT_FPT_API_KEY = os.getenv("FPT_API_KEY")
DEFAULT_FPT_BASE_URL = os.getenv("FPT_BASE_URL", "https://mkp-api.fptcloud.com/v1")
DEFAULT_FPT_MODEL = os.getenv("FPT_MODEL", "Llama-3.3-70B-Instruct")
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))
DEFAULT_TEMPERATURE = float(os.getenv("GENERATION_TEMPERATURE", "0.1"))
DEFAULT_TOP_P = float(os.getenv("GENERATION_TOP_P", "0.95"))
DEFAULT_TOP_K = int(os.getenv("GENERATION_TOP_K", "40"))
DEFAULT_PRESENCE_PENALTY = float(os.getenv("GENERATION_PRESENCE_PENALTY", "0"))
DEFAULT_FREQUENCY_PENALTY = float(os.getenv("GENERATION_FREQUENCY_PENALTY", "0"))

SYSTEM_PROMPT = """
Bạn là trợ lý tra cứu pháp luật Việt Nam. Nhiệm vụ của bạn là giúp người dùng
hiểu và áp dụng đúng thông tin trong các nguồn được cung cấp.

Nguyên tắc:
- Trả lời đúng trọng tâm và phù hợp với cách đặt câu hỏi của người dùng.
- Chủ động tổng hợp, diễn giải và nhóm các quy định liên quan thành câu trả lời tự nhiên, dễ hiểu.
- Khi nguồn thể hiện nhiều trường hợp hoặc cách xử lý, trình bày thành các phương án rõ ràng.
- Chỉ nêu phương án, điều kiện, ngoại lệ hoặc kết luận khi chúng được nguồn hỗ trợ.
- Không sử dụng kiến thức bên ngoài để bổ sung dữ kiện pháp lý còn thiếu.
- Không biến khả năng hoặc điều kiện trong nguồn thành một kết luận chắc chắn.
- Mỗi nhận định pháp lý quan trọng phải có mã nguồn tương ứng, ví dụ [S1].
- Có thể dùng một mã nguồn cho cả đoạn nếu toàn bộ đoạn dựa trên cùng nguồn.

Cách xử lý khi thiếu thông tin:
- Nếu đủ căn cứ: trả lời rõ ràng và trực tiếp, nêu rõ căn cứ.
- Nếu chỉ đủ căn cứ cho một phần: trả lời phần đó và nêu rõ căn cứ, đồng thời nêu thông tin còn thiếu.
- Nếu có nhiều cách hiểu hợp lý: trình bày từng cách hiểu và căn cứ nhưng vẫn bám sát vào câu hỏi, không tự chọn thay người dùng.
- Nếu không đủ căn cứ: nói rõ chưa thể kết luận từ các nguồn hiện có.

Ưu tiên diễn giải bằng lời của bạn. Chỉ trích nguyên văn khi câu chữ chính xác
của quy định là cần thiết để trả lời câu hỏi.
"""


class FPTAIClient:
    def __init__(self, api_key=DEFAULT_FPT_API_KEY, base_url=DEFAULT_FPT_BASE_URL, model=DEFAULT_FPT_MODEL):
        if not api_key:
            raise RuntimeError("FPT_API_KEY is not set. Add FPT_API_KEY=your_api_key to your .env file.")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def create_completion(
        self,
        prompt,
        max_tokens,
        temperature,
        top_p,
        top_k,
        presence_penalty,
        frequency_penalty,
    ):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "rag-law-vn/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FPT AI API error {exc.code} at {request.full_url}: {error_body}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"Could not connect to FPT AI API: {exc}") from exc

        return extract_answer(data)


def extract_answer(data):
    if isinstance(data.get("data"), dict):
        data = data["data"]

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"FPT AI API response has no choices: {data}")

    first_choice = choices[0]
    message = first_choice.get("message") or {}
    content = message.get("content") or first_choice.get("text")
    if content is None:
        raise RuntimeError(f"FPT AI API response has no answer content: {data}")

    return content.strip()


def load_generation_model():
    return FPTAIClient()


def generate_answer(
    model,
    query,
    max_new_tokens=DEFAULT_MAX_NEW_TOKENS,
    temperature=DEFAULT_TEMPERATURE,
    top_p=DEFAULT_TOP_P,
    top_k=DEFAULT_TOP_K,
    presence_penalty=DEFAULT_PRESENCE_PENALTY,
    frequency_penalty=DEFAULT_FREQUENCY_PENALTY,
    retrieval_resources=None,
):
    timings = {}
    total_started_at = time.perf_counter()

    try:
        print("Retrieving...")
        context, _sources = build_context(
            query,
            retrieval_resources=retrieval_resources,
            timings=timings,
        )
        print("Building prompt...")
        prompt = build_prompt(query, context)
        print(prompt)
        print(f"Generating answer with {model.model} via FPT AI...")

        generation_started_at = time.perf_counter()
        try:
            return model.create_completion(
                prompt=prompt,
                max_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
            )
        finally:
            timings["generation_ms"] = round(
                (time.perf_counter() - generation_started_at) * 1000,
                2,
            )
    finally:
        timings["total_ms"] = round(
            (time.perf_counter() - total_started_at) * 1000,
            2,
        )
        print(f"[latency] {json.dumps(timings, ensure_ascii=True, sort_keys=True)}")


def build_context(query, timings=None, retrieval_resources=None):
    results = retrieve(
        query,
        retrieval_resources,
        n_results=5,
        timings=timings,
    )
    sources = []

    for index, result in enumerate(results):
        metadata = result["metadata"]
        sources.append(
            {
                "id": f"[S{index + 1}]",
                "document": result["document"],
                "metadata": metadata,
                "dieu": metadata["dieu"],
                "rerank_score": result.get("rerank_score"),
            }
        )

    context = "\n\n".join(
        f"{source['id']}\n"
        f"Van ban: {source['metadata']['ten_vbpl']}\n"
        f"Dieu: {source['dieu']}\n"
        f"Noi dung: {source['document']}"
        for source in sources
    )
    return context, sources


def build_prompt(query, context):
    return f"""
### Nguon:
{context}

### Cau hoi can tra loi:
{query}

### Tra loi:
"""


def run_interactive(model, retrieval_resources):
    print("\nModel da san sang. Nhap cau hoi moi hoac go 'exit' de thoat.")
    while True:
        try:
            query = input("\nCau hoi: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDa thoat.")
            return

        if query.lower() in {"exit", "quit", "q"}:
            print("Da thoat.")
            return
        if not query:
            continue

        answer = generate_answer(
            model=model,
            query=query,
            retrieval_resources=retrieval_resources,
        )
        print(f"\nTra loi:\n{answer}")


def main():
    model = load_generation_model()
    retrieval_resources = RetrievalResources()
    run_interactive(model, retrieval_resources)


if __name__ == "__main__":
    main()
