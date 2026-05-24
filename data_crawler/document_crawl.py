import os

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.types import Text, String


GATEWAY_BASE_URL = os.getenv(
    "VBPL_GATEWAY_BASE_URL",
    "https://vbpl-bientap-gateway.moj.gov.vn",
).rstrip("/")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*;q=0.9, text/html;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Origin": "https://vbpl.vn",
        "Referer": "https://vbpl.vn/",
    }
)


# Create database connection
url = URL.create(
    drivername="mysql+pymysql",
    username="root",
    password="@12345@",
    host="localhost",
    port=2402,
    database="law_db",
)

engine = create_engine(url)


def ensure_vbpl_table_schema():
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS vbpl"))
        conn.execute(
            text(
                """
                CREATE TABLE vbpl (
                    id VARCHAR(32) NOT NULL,
                    html LONGTEXT NULL,
                    status_name VARCHAR(255) NULL,
                    PRIMARY KEY (id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
        )


ensure_vbpl_table_schema()

# Read source data from database
df = pd.read_sql(
    "SELECT id_vbqppl FROM pddieu WHERE id_vbqppl IS NOT NULL GROUP BY id_vbqppl;",
    con=engine,
)


def save_data(records):
    df_to_write = pd.DataFrame(records)
    if not df_to_write.empty:
        df_to_write.to_sql(
            "vbpl",
            con=engine,
            if_exists="append",
            index=False,
            dtype={
                "id": String(32),
                "html": Text(),
                "status_name": String(255),
            },
        )


def build_detail_url(doc_id):
    return f"https://vbpl.vn/van-ban/chi-tiet/{doc_id}?tabs=toan-van"


def build_gateway_url(doc_id):
    return f"{GATEWAY_BASE_URL}/api/qtdc/public/doc/{doc_id}"


def extract_first_content(payload):
    if isinstance(payload, dict):
        for key in ("documentContent", "documentContentEn"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                content = nested.get("content")
                if isinstance(content, str) and content.strip():
                    return content

        for key in ("data", "result", "items", "item"):
            nested = payload.get(key)
            content = extract_first_content(nested)
            if content:
                return content

        for value in payload.values():
            content = extract_first_content(value)
            if content:
                return content

    if isinstance(payload, list):
        for item in payload:
            content = extract_first_content(item)
            if content:
                return content

    return None


def normalize_html(content):
    if content is None:
        return None

    html = str(content).strip()
    return html or None


def build_document_record(
    doc_id,
    html=None,
    status_name=None,
):
    return {
        "id": doc_id,
        "html": normalize_html(html),
        "status_name": status_name,
    }


def extract_document_record(doc_id, api_payload):
    data = api_payload.get("data") if isinstance(api_payload, dict) else None
    eff_status = data.get("effStatus") if isinstance(data, dict) else None

    if not isinstance(eff_status, dict):
        eff_status = {}

    return build_document_record(
        doc_id=doc_id,
        html=extract_first_content(api_payload),
        status_name=eff_status.get("name"),
    )


def fetch_document_from_api(doc_id):
    api_url = build_gateway_url(doc_id)
    api_response = SESSION.get(
        api_url,
        timeout=10,
        headers={"Accept": "application/json, text/plain, */*"},
    )

    if api_response.status_code != 200:
        return None, api_response.status_code

    try:
        api_payload = api_response.json()
    except ValueError:
        return None, api_response.status_code

    document_record = extract_document_record(doc_id, api_payload)
    return document_record, api_response.status_code


def fetch_detail_page(doc_id):
    detail_url = build_detail_url(doc_id)
    page_response = SESSION.get(detail_url, timeout=10)

    if page_response.status_code != 200:
        raise RuntimeError(f"detail page returned {page_response.status_code}")

    return page_response


def extract_html_from_detail_page(doc_id, page_response):
    soup = BeautifulSoup(page_response.text, "html.parser")
    fulltexts = soup.find_all("div", class_="fulltext")
    print("html fulltext count:", len(fulltexts))

    if fulltexts:
        div_children = fulltexts[0].find_all("div")
        if len(div_children) > 1:
            html = normalize_html(str(div_children[1]))
            if not html:
                raise RuntimeError(f"empty html content for document id {doc_id}")
            print(f"[{doc_id}] source=html length={len(html)}")
            return html

    raise RuntimeError(f"Không có content với id {doc_id}")


def fetch_document_record_nextjs(doc_id):
    document_record, api_status = fetch_document_from_api(doc_id)
    if document_record and document_record["html"]:
        print(f"[{doc_id}] source=api length={len(document_record['html'])}")
        return document_record

    if api_status not in (200, 403, 404):
        raise RuntimeError(f"api returned {api_status}")

    # Bootstrap session/cookies from the detail page before retrying the API.
    page_response = fetch_detail_page(doc_id)
    retry_record, retry_status = fetch_document_from_api(doc_id)
    if retry_record and retry_record["html"]:
        print(f"[{doc_id}] source=api_after_bootstrap length={len(retry_record['html'])}")
        return retry_record

    print(f"[{doc_id}] api status={api_status}, retry status={retry_status}, fallback=html")
    fallback_record = retry_record or document_record or build_document_record(doc_id)
    fallback_record["html"] = extract_html_from_detail_page(doc_id, page_response)
    return fallback_record


list_vb = [str(df.iloc[i]["id_vbqppl"]).strip() for i in range(len(df))]

print(len(df))

df_vb = pd.DataFrame(list_vb)
df_vb = df_vb.dropna()
df_vb = df_vb.drop_duplicates()

print(len(df_vb))

records = []
for i in range(len(df_vb)):
    doc_id = str(df_vb.iloc[i][0])
    print(i, "Get data id", doc_id)

    try:
        record = fetch_document_record_nextjs(doc_id)
        records.append(record)
    except Exception as e:
        print(f"Get data id {doc_id} failed: {e}")
        continue


save_data(records)
