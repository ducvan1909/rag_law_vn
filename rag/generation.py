import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from retrieval import retrieve

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
Trả lời ngắn gọn và trực tiếp
Không suy diễn hoặc bổ sung ngoại lệ
Nếu nguồn không đủ thông tin, trả lời: Không đủ thông tin để trả lời.
Nếu có đủ thông tin thì mỗi câu phải kết thúc bằng ít nhất một mã nguồn theo đúng dạng [S1].
Chỉ trả lời dựa trên thông tin nằm trong nguồn.
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
):
    print("Retrieving...")
    context, _sources = build_context(query)
    print("Building prompt...")
    prompt = build_prompt(query, context)
    print(prompt)
    print(f"Generating answer with {model.model} via FPT AI...")
    return model.create_completion(
        prompt=prompt,
        max_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
    )


def build_context(query):
    results = retrieve(query, n_results=5)
    sources = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    for index in range(len(documents)):
        sources.append(
            {
                "id": f"[S{index + 1}]",
                "document": documents[index],
                "metadata": metadatas[index],
                "dieu": metadatas[index]["dieu"],
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


def run_interactive(model):
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

        answer = generate_answer(model=model, query=query)
        print(f"\nTra loi:\n{answer}")


def main():
    model = load_generation_model()
    run_interactive(model)


if __name__ == "__main__":
    main()
