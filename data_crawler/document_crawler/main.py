import os
import re
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, inspect, text
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
    inspector = inspect(engine)
    if not inspector.has_table("vbpl"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE vbpl (
                        id VARCHAR(32) NULL,
                        noidung LONGTEXT NULL
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE vbpl MODIFY COLUMN id VARCHAR(32) NULL"))
        conn.execute(text("ALTER TABLE vbpl MODIFY COLUMN noidung LONGTEXT NULL"))


ensure_vbpl_table_schema()


def clear_vbpl_table():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE vbpl"))


clear_vbpl_table()

# Read source data from database
df = pd.read_sql("SELECT link_vbqppl FROM pddieu GROUP BY link_vbqppl;", con=engine)


def get_infor(href):
    if href is None:
        return None

    href = str(href).strip()
    if not href:
        return None

    parsed = urlparse(href)
    path = parsed.path.rstrip("/")

    match = re.search(r"/van-ban/chi-tiet/(?:.*-)?(\d+)$", path)
    if match:
        return match.group(1)

    match = re.search(r"ItemID=(\d+)", href)
    if match:
        return match.group(1)

    query_item_id = parse_qs(parsed.query).get("ItemID")
    if query_item_id and query_item_id[0].isdigit():
        return query_item_id[0]

    match = re.search(r"(\d+)(?:\?.*)?$", path)
    if match:
        return match.group(1)

    print(f"Could not extract document id from link: {href}")
    return None


def save_data(list_id, list_noidung):
    df_to_write = pd.DataFrame(
        {
            "id": list_id,
            "noidung": list_noidung,
        }
    )
    if not df_to_write.empty:
        df_to_write.to_sql(
            "vbpl",
            con=engine,
            if_exists="append",
            index=False,
            dtype={"id": String(32), "noidung": Text()},
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


def html_to_text(content):
    if content is None:
        return None

    html = str(content).strip()
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    return text or None


def fetch_noidung_nextjs(doc_id):
    detail_url = build_detail_url(doc_id)
    page_response = SESSION.get(detail_url, timeout=10)


    if page_response.status_code != 200:
        raise RuntimeError(f"detail page returned {page_response.status_code}")

    api_url = build_gateway_url(doc_id)
    api_response = SESSION.get(api_url, timeout=10, headers={"Accept": "application/json, text/plain, */*"})


    if api_response.status_code == 200:
        try:
            api_payload = api_response.json()
        except ValueError:
            api_payload = None

        content = html_to_text(extract_first_content(api_payload))
        if content:
            print(f"[{doc_id}] source=api length={len(content)}")
            print(content)
            return content
    else:
        print(f"[{doc_id}] api status={api_response.status_code}, fallback=html")

    soup = BeautifulSoup(page_response.text, "html.parser")
    fulltexts = soup.find_all("div", class_="fulltext")
    print("html fulltext count:", len(fulltexts))

    if fulltexts:
        div_children = fulltexts[0].find_all("div")
        if len(div_children) > 1:
            content = html_to_text(str(div_children[1]))
            if not content:
                raise RuntimeError(f"empty html content for document id {doc_id}")
            print(f"[{doc_id}] source=html length={len(content)}")
            print(content)
            return content

    raise RuntimeError(f"Không có content với id {doc_id}")


list_vb = [get_infor(df.iloc[i]["link_vbqppl"]) for i in range(len(df))]

print(len(df))

df_vb = pd.DataFrame(list_vb)
df_vb = df_vb.dropna()
df_vb = df_vb.drop_duplicates()

print(len(df_vb))

list_id = []
list_noidung = []

for i in range(len(df_vb)):
    doc_id = str(df_vb.iloc[i][0])
    print(i, "Get data id", doc_id)

    try:
        noidung = fetch_noidung_nextjs(doc_id)
        list_id.append(doc_id)
        list_noidung.append(str(noidung))
    except Exception as e:
        print(f"Get data id {doc_id} failed: {e}")
        continue

    if (i + 1) % 10 == 0:
        save_data(list_id, list_noidung)
        list_id.clear()
        list_noidung.clear()


save_data(list_id, list_noidung)
