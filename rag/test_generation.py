import os
import sys
import ctypes
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


_DLL_DIRECTORY_HANDLES = []
_DLL_HANDLES = []


def add_windows_dll_directories():
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return

    candidates = [Path(path) / "llama_cpp" / "lib" for path in sys.path]
    cuda_path = os.getenv("CUDA_PATH")
    if cuda_path:
        candidates.extend([Path(cuda_path) / "bin", Path(cuda_path) / "lib"])

    cuda_root = Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "NVIDIA GPU Computing Toolkit" / "CUDA"
    if cuda_root.is_dir():
        for toolkit_path in cuda_root.glob("v*"):
            candidates.extend([toolkit_path / "bin", toolkit_path / "lib"])

    for path in candidates:
        if path.is_dir():
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(path)))

    for path in candidates:
        llama_dll = path / "llama.dll"
        if llama_dll.is_file():
            _DLL_HANDLES.append(ctypes.CDLL(str(llama_dll)))
            break


add_windows_dll_directories()

from llama_cpp import Llama

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

DEFAULT_MODEL_REPO = os.getenv("GENERATION_MODEL_REPO", "vinai/PhoGPT-4B-Chat-gguf")
DEFAULT_MODEL_FILENAME = os.getenv("GENERATION_MODEL_FILENAME", "PhoGPT-4B-Chat-Q4_K_M.gguf")
DEFAULT_HF_TOKEN = os.getenv("HF_TOKEN")
DEFAULT_QUESTION = os.getenv("GENERATION_QUESTION", "Trình bày về thủ tục ly hôn thuận tình tại Việt Nam.")
DEFAULT_CONTEXT_LENGTH = int(os.getenv("GENERATION_CONTEXT_LENGTH", "2048"))
DEFAULT_GPU_LAYERS = int(os.getenv("GENERATION_GPU_LAYERS", "-1"))
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))
DEFAULT_TEMPERATURE = float(os.getenv("GENERATION_TEMPERATURE", "0.1"))
DEFAULT_TOP_P = float(os.getenv("GENERATION_TOP_P", "0.95"))
DEFAULT_TOP_K = int(os.getenv("GENERATION_TOP_K", "40"))

SYSTEM_PROMPT = (
    "Bạn là trợ lý pháp luật Việt Nam. "
    "Chỉ trả lời dựa trên dữ liệu được cung cấp. "
    "Nếu dữ liệu không đủ để trả lời chính xác, hãy nói rõ rằng bạn không biết."
)


def load_generation_model(model_repo, model_filename, hf_token=None):
    if hf_token:
        # huggingface-hub reads HF_TOKEN from the environment inside from_pretrained().
        os.environ["HF_TOKEN"] = hf_token
    else:
        print("Warning: HF_TOKEN is not set. Public model download still works with a lower rate limit.")

    return Llama.from_pretrained(
        repo_id=model_repo,
        filename=model_filename,
        n_ctx=DEFAULT_CONTEXT_LENGTH,
        n_gpu_layers=DEFAULT_GPU_LAYERS,
        verbose=True,
    )


def generate_answer(model, question, max_new_tokens, temperature, top_p, top_k):
    instruction = f"{SYSTEM_PROMPT}\n\n{question}"
    response = model.create_completion(
        prompt=f"### Câu hỏi: {instruction}\n### Trả lời:",
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repeat_penalty=1.1,
        max_tokens=max_new_tokens,
        stop=["</s>", "### Câu hỏi:"],
    )
    return response["choices"][0]["text"].strip()


def main():
    model = load_generation_model(
        model_repo=DEFAULT_MODEL_REPO,
        model_filename=DEFAULT_MODEL_FILENAME,
        hf_token=DEFAULT_HF_TOKEN,
    )
    answer = generate_answer(
        model=model,
        question=DEFAULT_QUESTION,
        max_new_tokens=DEFAULT_MAX_NEW_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
        top_p=DEFAULT_TOP_P,
        top_k=DEFAULT_TOP_K,
    )
    print(answer)


if __name__ == "__main__":
    main()
