import argparse
import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, PretrainedConfig
from transformers.models.mpt.configuration_mpt import MptConfig

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

DEFAULT_MODEL_NAME = os.getenv("GENERATION_MODEL", "vinai/PhoGPT-4B-Chat")
DEFAULT_HF_TOKEN = os.getenv("HF_TOKEN")
DEFAULT_QUESTION = os.getenv("GENERATION_QUESTION", "Trình bày về thủ tục li hôn ?")
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "256"))

PROMPT = """
### Hướng dẫn: Bạn là một trợ lí Tiếng Việt. Hãy luôn trả lời một cách trung thực và an toàn
Câu trả lời của bạn không nên chứa bất kỳ nội dung gây hại, nguy hiểm hoặc bất hợp pháp nào
Nếu một câu hỏi không có ý nghĩa hoặc không hợp lý về mặt thông tin, hãy giải thích tại sao thay vì trả lời một điều gì đó không chính xác
Nếu bạn không biết câu trả lời cho một câu hỏi, hãy trả lời là bạn không biết và vui lòng không chia sẻ thông tin sai lệch.
### Câu hỏi: {input}
### Trả lời:
"""


def parse_args():
    parser = argparse.ArgumentParser(description="Run a local text-generation smoke test.")
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--hf-token", default=DEFAULT_HF_TOKEN)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--max-new-tokens", type=int, default=DEFAULT_MAX_NEW_TOKENS)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--top-k", type=int, default=40)
    parser.add_argument("--prompt-only", action="store_true")
    return parser.parse_args()


def resolve_device():
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


def build_prompt(question):
    return PROMPT.format_map({"input": question})


def load_model_config(model_name, hf_token=None):
    config_dict, _ = PretrainedConfig.get_config_dict(model_name, token=hf_token)
    if config_dict.get("model_type") == "mpt":
        # transformers 5.5.0 in this environment incorrectly types attn_pdrop as int.
        attn_config = dict(config_dict.get("attn_config") or {})
        attn_pdrop = attn_config.get("attn_pdrop")
        if isinstance(attn_pdrop, float) and attn_pdrop.is_integer():
            attn_config["attn_pdrop"] = int(attn_pdrop)
            config_dict["attn_config"] = attn_config
        return MptConfig.from_dict(config_dict)
    return None


def load_generation_model(model_name, hf_token=None):
    device, torch_dtype = resolve_device()
    tokenizer = AutoTokenizer.from_pretrained(model_name, token=hf_token)
    if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
        tokenizer.pad_token = tokenizer.eos_token

    config = load_model_config(model_name, hf_token=hf_token)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        config=config,
        token=hf_token,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()
    return model, tokenizer, device


def generate_answer(model, tokenizer, prompt, max_new_tokens, temperature, top_p, top_k):
    encoded = tokenizer(prompt, return_tensors="pt")
    encoded = {key: value.to(model.device) for key, value in encoded.items()}

    with torch.inference_mode():
        generated_ids = model.generate(
            **encoded,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    prompt_tokens = encoded["input_ids"].shape[-1]
    answer_ids = generated_ids[0][prompt_tokens:]
    return tokenizer.decode(answer_ids, skip_special_tokens=True).strip()


def main():
    args = parse_args()
    prompt = build_prompt(args.question)
    print(prompt)

    if args.prompt_only:
        return

    model, tokenizer, device = load_generation_model(args.model_name, hf_token=args.hf_token)
    if device == "cpu":
        print("Warning: running a 4B causal LM on CPU can be very slow and memory intensive.")

    answer = generate_answer(
        model=model,
        tokenizer=tokenizer,
        prompt=prompt,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
    )
    print(answer)


if __name__ == "__main__":
    main()
