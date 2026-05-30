import os
from sentence_transformers import SentenceTransformer

from database.db_config import db
from database.mysql_model import VBPLUnit

MAX_TOKENS = 700

model_name = os.getenv("EMBEDDING_MODEL", "truro7/vn-law-embedding")
hf_token = os.getenv("HF_TOKEN")

embedding_model = SentenceTransformer(model_name, token=hf_token)

def get_vbpl_unit(limit=100):
    db.connect(reuse_if_open=True)

    query = (
        VBPLUnit
        .select()
        .where(VBPLUnit.content.is_null(False) and VBPLUnit.content != "")
        .limit(limit)
        .dicts()
    )

    rows = list(query)

    db.close()
    return rows

def get_content(limit=100):
    db.connect(reuse_if_open=True)

    query = (
        VBPLUnit
        .select(VBPLUnit.content)
        .where(VBPLUnit.content.is_null(False) and VBPLUnit.content != "")
        .limit(limit)
        .dicts()
    )

    db.close()
    rows = list(query)
    print(rows)

    return rows

get_content(2)

def get_tokens_length(tokenizer, corpus):
    tokens = tokenizer.encode(corpus, add_special_tokens=False)
    return len(tokens)



