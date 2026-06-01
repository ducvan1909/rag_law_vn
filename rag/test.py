import os
import sys
from pathlib import Path

import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM, AutoTokenizer, PretrainedConfig
from transformers.models.mpt.configuration_mpt import MptConfig

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

DEFAULT_MODEL_NAME = os.getenv("GENERATION_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
DEFAULT_HF_TOKEN = os.getenv("HF_TOKEN")
QUESTION = "Trình bày về thủ tục ly hôn?"
MAX_NEW_TOKENS = 256
TEMPERATURE = 0.3
TOP_P = 0.95
TOP_K = 40

PROMPT = """You are a helpful Vietnamese assistant that answer questions about Vietnam Legal problems.
Question: {input}
Answer:
"""
def load_config(model_name, hf_token=None):
    config_dict, _ = PretrainedConfig.get_config_dict(model_name, token=hf_token)
    if config_dict.get("model_type") != "mpt":
        return None

    attn_config = dict(config_dict.get("attn_config") or {})
    attn_pdrop = attn_config.get("attn_pdrop")
    if isinstance(attn_pdrop, float) and attn_pdrop.is_integer():
        attn_config["attn_pdrop"] = int(attn_pdrop)
        config_dict["attn_config"] = attn_config

    return MptConfig.from_dict(config_dict)


def build_inputs(tokenizer, question, device):
    if getattr(tokenizer, "chat_template", None):
        messages = [
            {"role": "system", "content": "You are a helpful Vietnamese assistant."},
            {"role": "user", "content": question},
        ]
        inputs = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )
    else:
        prompt = PROMPT.format(input=question)
        inputs = tokenizer(prompt, return_tensors="pt")

    return {key: value.to(device) for key, value in inputs.items()}


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    torch_dtype = torch.bfloat16 if device == "cuda" else torch.float32
    config = load_config(DEFAULT_MODEL_NAME, DEFAULT_HF_TOKEN)

    tokenizer_kwargs = {"token": DEFAULT_HF_TOKEN}
    if config is not None:
        tokenizer_kwargs["config"] = config

    tokenizer = AutoTokenizer.from_pretrained(DEFAULT_MODEL_NAME, **tokenizer_kwargs)
    if tokenizer.pad_token_id is None and tokenizer.eos_token_id is not None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        DEFAULT_MODEL_NAME,
        config=config,
        token=DEFAULT_HF_TOKEN,
        torch_dtype=torch_dtype,
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()

    inputs = build_inputs(tokenizer, QUESTION, device)

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            top_k=TOP_K,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    answer_ids = outputs[0][inputs["input_ids"].shape[-1] :]
    answer = tokenizer.decode(answer_ids, skip_special_tokens=True).strip()
    print(answer)


if __name__ == "__main__":
    main()
