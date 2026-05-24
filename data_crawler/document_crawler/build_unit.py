import sys
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

from db_config import db
from db_models.mysql_model import PDChuDe, PDChuong, PDDeMuc, PDDieu


CONTENT_PROV_CLASSES = {
    "prov-clause",
    "prov-item",
    "prov-point",
    "prov-sub-item",
    "prov-sub-point",
    "prov-paragraph",
}

STRUCTURAL_BREAK_PREFIXES = ("chương ", "mục ", "phần ")


def prov_classes(node):
    return [cls for cls in (node.get("class") or []) if cls.startswith("prov-")]


def ensure_output_tables():
    with db.atomic():
        db.execute_sql("DROP TABLE IF EXISTS vbpl_unit")
        db.execute_sql("DROP TABLE IF EXISTS vbpl_document")
        db.execute_sql(
            """
            CREATE TABLE vbpl_document (
              id VARCHAR(32) NOT NULL,
              plain_text LONGTEXT NULL,
              status_name VARCHAR(255) NULL,
              PRIMARY KEY (id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
            """
        )
        db.execute_sql(
            """
            CREATE TABLE vbpl_unit (
              id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
              document_id VARCHAR(32) NOT NULL,
              dieu_id VARCHAR(128) NOT NULL,
              dieu VARCHAR(255) NOT NULL,
              chuong VARCHAR(255) NOT NULL,
              demuc VARCHAR(255) NOT NULL,
              chude VARCHAR(255) NOT NULL,
              ten_vbpl TEXT NOT NULL,
              content LONGTEXT NOT NULL,
              char_start INT NULL,
              char_end INT NULL,
              status_name VARCHAR(255) NULL,
              KEY idx_vbpl_unit_document_id (document_id),
              KEY idx_vbpl_unit_dieu_id (dieu_id),
              CONSTRAINT fk_unit_document FOREIGN KEY (document_id) REFERENCES vbpl_document(id),
              CONSTRAINT fk_unit_dieu FOREIGN KEY (dieu_id) REFERENCES pddieu(dieu_id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
            """
        )


def fetch_dieu_rows():
    query = (
        PDDieu.select(
            PDDieu.dieu_id.alias("dieu_id"),
            PDDieu.ten.alias("dieu"),
            PDDieu.ten_vbqppl.alias("ten_vbpl"),
            PDDieu.id_vbqppl.alias("document_id"),
            PDChuong.ten.alias("chuong"),
            PDDeMuc.ten.alias("demuc"),
            PDChuDe.ten.alias("chude"),
        )
        .join(PDChuong)
        .switch(PDDieu)
        .join(PDDeMuc)
        .switch(PDDieu)
        .join(PDChuDe)
        .where(PDDieu.id_vbqppl.is_null(False))
        .dicts()
    )
    return list(query)


def fetch_vbpl_documents(document_ids, chunk_size=500):
    documents = {}
    sorted_ids = sorted({str(doc_id).strip() for doc_id in document_ids if doc_id})

    for start in range(0, len(sorted_ids), chunk_size):
        chunk = sorted_ids[start : start + chunk_size]
        placeholders = ",".join(["%s"] * len(chunk))
        cursor = db.execute_sql(
            f"SELECT id, html, status_name FROM vbpl WHERE id IN ({placeholders})",
            chunk,
        )
        for doc_id, html, status_name in cursor.fetchall():
            documents[str(doc_id)] = {
                "id": str(doc_id),
                "html": html,
                "status_name": status_name,
            }

    return documents


def normalize_whitespace(text):
    if text is None:
        return None

    normalized = unicodedata.normalize("NFKC", str(text)).replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n[ \t]+", "\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = normalized.strip()
    return normalized or None


def normalize_match_text(text):
    normalized = normalize_whitespace(text)
    if not normalized:
        return ""

    normalized = normalized.casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    return normalized.strip()


def node_to_text(node):
    if node is None:
        return ""

    text = node.get_text(separator="\n", strip=True)
    return normalize_whitespace(text) or ""


def resolve_root_container(soup):
    body = soup.body or soup
    if getattr(body, "name", None) == "body":
        direct_tags = [child for child in body.children if getattr(child, "name", None) is not None]
        if len(direct_tags) == 1 and direct_tags[0].name == "div":
            return direct_tags[0]
    return body


def iter_block_nodes(root):
    for node in root.find_all(True):
        if node.name in {"p", "li"}:
            yield node
            continue

        if node.name == "div":
            if node.find(["p", "li"], recursive=True) is None:
                yield node
            continue

        if prov_classes(node):
            if node.find(["p", "li"], recursive=True) is None:
                yield node


def extract_part_meta(raw_heading):
    heading = normalize_whitespace(raw_heading) or ""
    heading = heading.replace("\n", " ")
    heading = re.sub(r"\s{2,}", " ", heading).strip()

    match = re.match(r"^([IVXLCDM]+)[.)]?\s+(.*)$", heading, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper(), match.group(2).strip(" :.-")

    return None, heading


def classify_node(node, text, has_prov_article):
    classes = prov_classes(node)
    if "prov-article" in classes:
        return "article"
    if any(cls in CONTENT_PROV_CLASSES for cls in classes):
        return "content"
    if not has_prov_article and "prov-part" in classes:
        return "article"
    if classes:
        return "boundary"

    if has_prov_article:
        return "content"

    article_no, _ = extract_article_meta(text)
    if article_no:
        return "article"

    normalized_text = normalize_whitespace(text) or ""
    normalized_text = normalized_text.casefold()
    if normalized_text.startswith(("chương ", "mục ", "phần ")):
        return "boundary"

    return "content"


def extract_article_meta(raw_heading):
    heading = normalize_whitespace(raw_heading) or ""
    heading = heading.replace("\n", " ")
    heading = re.sub(r"\s{2,}", " ", heading).strip()

    if not heading.casefold().startswith("điều "):
        return None, heading

    body = heading[5:].strip()
    left, separator, title = body.partition(". ")
    if separator:
        article_no = left.split(".")[-1].strip()
        article_title = title.strip()
        return article_no or None, article_title

    match = re.match(r"^([0-9]+[a-zA-Z]?)(?:[.:]?\s*)(.*)$", body)
    if match:
        return match.group(1).strip() or None, match.group(2).strip()

    return None, body


def build_article_sections(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    root = resolve_root_container(soup)
    has_prov_article = root.find(class_="prov-article") is not None
    child_infos = []
    plain_parts = []
    cursor = 0

    for child in iter_block_nodes(root):
        text = node_to_text(child)
        if not text:
            continue

        if plain_parts:
            cursor += 2
        start = cursor
        end = start + len(text)
        cursor = end

        child_infos.append(
            {
                "node": child,
                "text": text,
                "start": start,
                "end": end,
                "kind": classify_node(child, text, has_prov_article),
                "classes": prov_classes(child),
            }
        )
        plain_parts.append(text)

    sections = []
    current_section = None

    for child_info in child_infos:
        kind = child_info["kind"]
        if kind == "article":
            if current_section is not None:
                sections.append(finalize_section(current_section))

            article_no, article_title = extract_article_meta(child_info["text"])
            if article_no is None and "prov-part" in child_info["classes"]:
                article_no, article_title = extract_part_meta(child_info["text"])
            current_section = {
                "heading_info": child_info,
                "article_no": article_no,
                "article_title": article_title,
                "content_infos": [],
            }
            continue

        if current_section is not None and kind == "boundary":
            normalized_text = normalize_whitespace(child_info["text"])
            if normalized_text and normalized_text.casefold().startswith(STRUCTURAL_BREAK_PREFIXES):
                sections.append(finalize_section(current_section))
                current_section = None
                continue

        if current_section is not None:
            current_section["content_infos"].append(child_info)

    if current_section is not None:
        sections.append(finalize_section(current_section))

    return "\n\n".join(plain_parts), sections


def finalize_section(section):
    content_infos = section["content_infos"]
    heading_info = section["heading_info"]

    if content_infos:
        content_text = "\n\n".join(info["text"] for info in content_infos)
        char_start = content_infos[0]["start"]
        char_end = content_infos[-1]["end"]
    else:
        content_text = heading_info["text"]
        char_start = heading_info["start"]
        char_end = heading_info["end"]

    article_no_key = normalize_match_text(section["article_no"])
    article_title_key = normalize_match_text(section["article_title"])

    return {
        "heading_text": heading_info["text"],
        "article_no": section["article_no"],
        "article_title": section["article_title"],
        "article_no_key": article_no_key,
        "article_title_key": article_title_key,
        "content_text": content_text,
        "char_start": char_start,
        "char_end": char_end,
    }


def build_section_indexes(sections):
    by_key = defaultdict(list)
    by_no = defaultdict(list)
    by_title = defaultdict(list)

    for section in sections:
        if section["article_no_key"]:
            by_no[section["article_no_key"]].append(section)
        if section["article_no_key"] and section["article_title_key"]:
            by_key[(section["article_no_key"], section["article_title_key"])].append(section)
        if section["article_title_key"]:
            by_title[section["article_title_key"]].append(section)

    return by_key, by_no, by_title


def choose_best_section(expected_title, candidates):
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    expected_key = normalize_match_text(expected_title)
    scored = []
    for candidate in candidates:
        score = SequenceMatcher(None, expected_key, candidate["article_title_key"]).ratio()
        scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) == 1:
        return scored[0][1]

    if scored[0][0] > scored[1][0]:
        return scored[0][1]

    return scored[0][1]


def match_section_for_dieu(dieu_name, by_key, by_no, by_title):
    article_no, article_title = extract_article_meta(dieu_name)
    article_no_key = normalize_match_text(article_no)
    article_title_key = normalize_match_text(article_title)

    exact_candidates = by_key.get((article_no_key, article_title_key), [])
    if exact_candidates:
        return choose_best_section(article_title, exact_candidates)

    number_candidates = by_no.get(article_no_key, [])
    if number_candidates:
        return choose_best_section(article_title, number_candidates)

    title_candidates = by_title.get(article_title_key, [])
    if title_candidates:
        return choose_best_section(article_title, title_candidates)

    return None


def group_dieu_rows_by_document(dieu_rows):
    grouped_rows = defaultdict(list)
    for row in dieu_rows:
        document_id = str(row["document_id"]).strip()
        if not document_id:
            continue
        row["document_id"] = document_id
        grouped_rows[document_id].append(row)
    return grouped_rows


def insert_document_rows(rows, batch_size=500):
    if not rows:
        return

    query = """
        INSERT INTO vbpl_document (id, plain_text, status_name)
        VALUES (%s, %s, %s)
    """
    with db.atomic():
        cursor = db.connection().cursor()
        for start in range(0, len(rows), batch_size):
            cursor.executemany(query, rows[start : start + batch_size])


def insert_unit_rows(rows, batch_size=500):
    if not rows:
        return

    query = """
        INSERT INTO vbpl_unit (
            document_id,
            dieu_id,
            dieu,
            chuong,
            demuc,
            chude,
            ten_vbpl,
            content,
            char_start,
            char_end,
            status_name
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with db.atomic():
        cursor = db.connection().cursor()
        for start in range(0, len(rows), batch_size):
            cursor.executemany(query, rows[start : start + batch_size])


def safe_string(value):
    if value is None:
        return ""
    return str(value).strip()


def main():
    db.connect(reuse_if_open=True)
    ensure_output_tables()

    dieu_rows = fetch_dieu_rows()
    dieu_by_document = group_dieu_rows_by_document(dieu_rows)
    vbpl_documents = fetch_vbpl_documents(dieu_by_document.keys())

    document_rows = []
    unit_rows = []
    unmatched_rows = []

    for document_id, rows in dieu_by_document.items():
        document = vbpl_documents.get(document_id)
        if document is None:
            print(f"[missing document] {document_id} referenced by {len(rows)} rows")
            for row in rows:
                unmatched_rows.append((document_id, row["dieu_id"], "missing_document"))
            continue

        plain_text, sections = build_article_sections(document.get("html"))
        document_rows.append((document_id, plain_text, document.get("status_name")))

        by_key, by_no, by_title = build_section_indexes(sections)
        matched_count = 0
        for row in rows:
            matched_section = match_section_for_dieu(row["dieu"], by_key, by_no, by_title)
            if matched_section is None:
                unmatched_rows.append((document_id, row["dieu_id"], row["dieu"]))
                continue

            unit_rows.append(
                (
                    document_id,
                    safe_string(row["dieu_id"]),
                    safe_string(row["dieu"])[:255],
                    safe_string(row["chuong"])[:255],
                    safe_string(row["demuc"])[:255],
                    safe_string(row["chude"])[:255],
                    safe_string(row["ten_vbpl"]),
                    safe_string(matched_section["content_text"]),
                    matched_section["char_start"],
                    matched_section["char_end"],
                    document.get("status_name"),
                )
            )
            matched_count += 1

        print(
            f"[{document_id}] sections={len(sections)} rows={len(rows)} "
            f"matched={matched_count} plain_text_len={len(plain_text or '')}"
        )

    insert_document_rows(document_rows)
    insert_unit_rows(unit_rows)

    print(f"documents inserted: {len(document_rows)}")
    print(f"units inserted: {len(unit_rows)}")
    print(f"unmatched rows: {len(unmatched_rows)}")

    for document_id, dieu_id, reason in unmatched_rows[:50]:
        print(f"[unmatched] document={document_id} dieu_id={dieu_id} reason={reason}")

    db.close()


if __name__ == "__main__":
    main()
