import os

import requests
from bs4 import BeautifulSoup
from peewee import chunked

from db_config import db
from mysql_model import PDDieu, VBPL_TABLES, VBPL, reset_tables


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

def ensure_vbpl_table_schema():
    reset_tables(VBPL_TABLES)


def fetch_document_ids():
    query = (
        PDDieu.select(PDDieu.id_vbqppl)
        .where(PDDieu.id_vbqppl.is_null(False))
        .group_by(PDDieu.id_vbqppl)
        .tuples()
    )
    document_ids = []
    seen = set()

    for (doc_id,) in query:
        normalized_id = str(doc_id).strip()
        if not normalized_id or normalized_id in seen:
            continue
        seen.add(normalized_id)
        document_ids.append(normalized_id)

    return document_ids


def save_data(records, batch_size=200):
    if not records:
        return

    with db.atomic():
        for batch in chunked(records, batch_size):
            VBPL.insert_many(list(batch)).execute()


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


def main():
    db.connect(reuse_if_open=True)
    try:
        ensure_vbpl_table_schema()
        document_ids = fetch_document_ids()
        print(f"documents to crawl: {len(document_ids)}")

        records = []
        inserted_count = 0
        for index, doc_id in enumerate(document_ids):
            print(index, "Get data id", doc_id)

            try:
                record = fetch_document_record_nextjs(doc_id)
                records.append(record)
            except Exception as e:
                print(f"Get data id {doc_id} failed: {e}")
                continue

            if len(records) >= 200:
                save_data(records)
                inserted_count += len(records)
                records.clear()

        if records:
            save_data(records)
            inserted_count += len(records)

        print(f"documents inserted: {inserted_count}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
