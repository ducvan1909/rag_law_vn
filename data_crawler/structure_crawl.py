import atexit
import json
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

# Resolve imports and local data files relative to this script.
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent
PHAP_DIEN_DIR = DATA_DIR / "phap-dien"
DEMUC_DIR = PHAP_DIEN_DIR / "demuc"

for path in (DATA_DIR, ROOT_DIR):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from database.mysql_model import *
from utils import *


def load_json_file(filename):
    with open(PHAP_DIEN_DIR / filename, "r", encoding="utf_8") as input_file:
        return json.load(input_file)


def main():
    start_time = time.perf_counter()

    def print_total_runtime():
        elapsed = time.perf_counter() - start_time
        print(f"\nTotal runtime: {elapsed:.2f} seconds")

    atexit.register(print_total_runtime)

    db.connect(reuse_if_open=True)

    try:
        reset_tables(STRUCTURE_TABLES, drop_tables=STRUCTURE_TABLES + VBPL_UNIT_TABLES)

        print("Load cac chu de")
        chudes = load_json_file("chude.json")

        print("Insert cac chu de")
        try:
            with db.atomic():
                PDChuDe.bulk_create(
                    [
                        PDChuDe(
                            chude_id=chude["Value"],
                            ten=chude["Text"],
                            stt=chude["STT"],
                        )
                        for chude in chudes
                    ]
                )
                print("Insert chu de thanh cong")
        except Exception as exc:
            print(f"Insert chu de loi: {exc}")

        print("Load cac de muc")
        demucs = load_json_file("demuc.json")
        demuc_dict = {demuc["Value"]: demuc for demuc in demucs}

        print("Insert cac de muc")
        try:
            with db.atomic():
                PDDeMuc.bulk_create(
                    [
                        PDDeMuc(
                            demuc_id=demuc["Value"],
                            chude_id=demuc["ChuDe"],
                            ten=demuc["Text"],
                            stt=demuc["STT"],
                        )
                        for demuc in demucs
                    ]
                )
                print("Insert de muc thanh cong")
        except Exception as exc:
            print(f"Insert de muc loi: {exc}")

        print("Load tree nodes")
        tree_nodes = load_json_file("treeNode.json")

        tree_nodes_dict = defaultdict(list)
        for node in tree_nodes:
            tree_nodes_dict[node["DeMucID"]].append(node)

        dieus_lienquan = []
        inserted_chuong = set()
        inserted_dieu = set()

        for filepath in sorted(DEMUC_DIR.iterdir()):
            if filepath.suffix != ".html":
                continue

            filename = filepath.name
            demuc_id = filepath.stem

            with open(filepath, "r", encoding="utf_8") as demuc_file:
                demuc_html = BeautifulSoup(demuc_file.read(), "html.parser")

            anchor_by_name = {}
            for anchor in demuc_html.find_all("a", attrs={"name": True}):
                anchor_name = anchor.get("name")
                if anchor_name is None:
                    continue
                if isinstance(anchor_name, list):
                    if not anchor_name:
                        continue
                    anchor_name = anchor_name[0]
                anchor_by_name[str(anchor_name)] = anchor

            demuc_node = tree_nodes_dict.get(demuc_id, [])
            demuc_chuong = [node for node in demuc_node if node["TEN"].startswith("Chương ")]
            demuc_dieu = [node for node in demuc_node if node["TEN"].startswith("Điều ")]

            if len(demuc_node) == 0:
                print("Khong ton tai node cho de muc: " + filename)
                continue

            chuongs_data = []
            for chuong in demuc_chuong:
                if chuong["MAPC"] in inserted_chuong:
                    continue
                try:
                    chuongs_data.append(
                        PDChuong(
                            chuong_id=chuong["MAPC"],
                            chimuc=chuong["ChiMuc"],
                            ten=chuong["TEN"],
                            stt=roman_to_int(chuong["ChiMuc"]),
                            demuc_id=demuc_id,
                        )
                    )
                    inserted_chuong.add(chuong["MAPC"])
                except Exception:
                    continue

            print(f"Inserted {len(chuongs_data)} chuong cua de muc {demuc_id}")

            with db.atomic():
                PDChuong.bulk_create(chuongs_data)

            if len(chuongs_data) == 0:
                chuong_data = PDChuong.create(
                    chuong_id=uuid.uuid4(),
                    chimuc="0",
                    ten="",
                    stt=0,
                    demuc_id=demuc_id,
                )
                chuongs_data.append(chuong_data)

            print(
                f"De muc {demuc_id} co {len(demuc_chuong)} chuong "
                f"va {len(demuc_dieu)} dieu"
            )

            stt = 0
            dieus_data = []
            tables = []
            files = []
            for dieu in demuc_dieu:
                if dieu["MAPC"] in inserted_dieu:
                    continue

                if len(chuongs_data) == 1:
                    chuong_id = chuongs_data[0].chuong_id
                else:
                    chuong_id = None
                    for chuong_data in chuongs_data:
                        if dieu["MAPC"].startswith(chuong_data.chuong_id):
                            chuong_id = chuong_data.chuong_id
                            break
                    if chuong_id is None:
                        chuong_id = chuongs_data[0].chuong_id

                demuc_meta = demuc_dict.get(dieu["DeMucID"])
                if not demuc_meta:
                    print(f"Khong tim thay de muc cho dieu {dieu['MAPC']}")
                    continue

                dieu_html = anchor_by_name.get(dieu["MAPC"])
                if not dieu_html:
                    print(f"Khong tim thay anchor cho {dieu['MAPC']}")
                    continue

                ghi_chu_html = dieu_html.parent.next_sibling
                vbqppl = ghi_chu_html.text if ghi_chu_html else None
                vbqppl_link = (
                    ghi_chu_html.select("a")[0]["href"]
                    if ghi_chu_html and ghi_chu_html.select("a")
                    else None
                )
                vbqppl_id = extract_vbpl_document_id(vbqppl_link)
                noidung_html = dieu_html.parent.find_next("p", {"class": "pNoiDung"})
                noidung = ""

                for content in noidung_html.contents:
                    if content.name == "table":
                        tables.append(PDBang(dieu_id=dieu["MAPC"], html=str(content)))
                        continue
                    noidung += str(content.text.strip()) + "\n"

                try:
                    dieus_data.append(
                        PDDieu(
                            dieu_id=dieu["MAPC"],
                            ten=dieu["TEN"],
                            stt=stt,
                            noi_dung=noidung,
                            chi_muc=dieu["ChiMuc"],
                            ten_vbqppl=vbqppl,
                            id_vbqppl=vbqppl_id,
                            chuong_id=chuong_id,
                            demuc_id=dieu["DeMucID"],
                            chude_id=demuc_meta["ChuDe"],
                        )
                    )
                    inserted_dieu.add(dieu["MAPC"])
                except Exception as exc:
                    print(f"Loi insert dieu {dieu['MAPC']}: {exc}")
                    continue

                element = noidung_html.next_sibling
                while element and element.name == "a":
                    link = element["href"]
                    try:
                        files.append(PDFile(dieu_id=dieu["MAPC"], link=link, path=""))
                    except Exception as exc:
                        print(f"Loi insert file {link}: {exc}")

                    element = element.next_sibling

                if (
                    element
                    and element.name == "p"
                    and element["class"]
                    and element["class"][0] == "pChiDan"
                ):
                    lienquans_html = element.select("a")
                    for lienquan_html in lienquans_html:
                        if "onclick" not in lienquan_html.attrs or lienquan_html["onclick"] == "":
                            continue
                        dieu_id_lienquan = extract_input(lienquan_html["onclick"]).replace(
                            "'",
                            "",
                        )
                        dieus_lienquan.append(
                            {"dieu_id1": dieu["MAPC"], "dieu_id2": dieu_id_lienquan}
                        )

                stt += 1

            with db.atomic():
                PDDieu.bulk_create(dieus_data)
                PDBang.bulk_create(tables)
                PDFile.bulk_create(files)

        dieus_lienquan_data = []
        for dieu_lienquan in dieus_lienquan:
            if dieu_lienquan["dieu_id1"] not in inserted_dieu:
                print(f'{dieu_lienquan["dieu_id1"]} khong ton tai')
                continue
            if dieu_lienquan["dieu_id2"] not in inserted_dieu:
                print(f'{dieu_lienquan["dieu_id2"]} khong ton tai')
                continue
            try:
                dieus_lienquan_data.append(
                    PDDieuLienQUan(
                        dieu1=dieu_lienquan["dieu_id1"],
                        dieu2=dieu_lienquan["dieu_id2"],
                    )
                )
            except Exception as exc:
                print(
                    "Khong the insert dieu lien quan "
                    f'{dieu_lienquan["dieu_id1"]} - {dieu_lienquan["dieu_id2"]}: {exc}'
                )

        with db.atomic():
            PDDieuLienQUan.bulk_create(dieus_lienquan_data)
    finally:
        if not db.is_closed():
            db.close()

main()
