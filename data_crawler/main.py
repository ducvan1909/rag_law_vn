import json
import pathlib
import os
import uuid
import time
import atexit

from collections import defaultdict
from bs4 import BeautifulSoup
from db_config import db
from db_models.mysql_model import *
from utils import *


start_time = time.perf_counter()
def print_total_runtime():
    elapsed = time.perf_counter() - start_time
    print(f"\nTotal runtime: {elapsed:.2f} seconds")
atexit.register(print_total_runtime)

# Kết nối với database và tạo bảng
db.connect(reuse_if_open=True)
db.drop_tables([PDChuDe, PDDeMuc, PDChuong, PDDieu, PDBang, PDFile, PDDieuLienQUan], safe=True)
db.create_tables([PDChuDe, PDDeMuc, PDChuong, PDDieu, PDBang, PDFile, PDDieuLienQUan], safe=True)

print("Load các chủ đề")
with open("./phap-dien/chude.json", "r", encoding="utf_8") as f_chude:
    chudes = json.load(f_chude)
f_chude.close()

print("Insert các chủ đề")
try:
    with db.atomic():
        PDChuDe.bulk_create([PDChuDe(chude_id=chude["Value"], ten=chude["Text"], stt=chude["STT"]) for chude in chudes])
        print("Insert chủ đề thành công")
except Exception as e:
    print(f"Insert chủ đề lỗi: {e}")

print("Load các đề mục")
with open("./phap-dien/demuc.json", "r", encoding="utf_8") as f_demuc:
    demucs = json.load(f_demuc)
f_demuc.close()
demuc_dict = {demuc["Value"]: demuc for demuc in demucs}

print("Insert các đề mục")
try:
    with db.atomic():
        PDDeMuc.bulk_create([PDDeMuc(demuc_id=demuc["Value"], chude_id=demuc["ChuDe"], ten=demuc["Text"], stt=demuc["STT"]) for demuc in demucs])
        print("Insert đề mục thành công")
except Exception as e:
    print(f"Insert đề mục lỗi: {e}")

print("Load tree nodes")
with open("./phap-dien/treeNode.json", "r", encoding="utf_8") as f_tree_nodes:
    tree_nodes = json.load(f_tree_nodes)
f_tree_nodes.close()

#Biến các node thành dictionary với key là DeMucID, value là list các node tương ứng
tree_nodes_dict = defaultdict(list)
for node in tree_nodes:
    tree_nodes_dict[node["DeMucID"]].append(node)

demuc_dir = pathlib.Path("./phap-dien/demuc")
dieus_lienquan = []

inserted_chuong = set()
inserted_dieu = set()

for file in os.listdir(demuc_dir):
    filename = os.fsdecode(file)
    if filename.endswith(".html"):
        filepath = os.path.join(demuc_dir, file)
        with open(filepath, "r", encoding="utf_8") as demuc_file:
            demuc_html = demuc_file.read()
            demuc_html = BeautifulSoup(demuc_html, "html.parser")
            demuc_node = tree_nodes_dict.get(filename.split(".")[0], [])
            demuc_chuong = [node for node in demuc_node if node["TEN"].startswith("Chương ")]
            demuc_dieu = [node for node in demuc_node if node["TEN"].startswith("Điều ")]

            if len(demuc_node) == 0:
                print("Không tồn tại node cho đề mục:" + filename)
                demuc_file.close()
                continue

            #Insert Chương vào db
            chuongs_data = []
            for chuong in demuc_chuong:
                if chuong["MAPC"] in inserted_chuong:
                    continue
                try:
                    chuongs_data.append(PDChuong(
                        chuong_id = chuong["MAPC"],
                        chimuc = chuong["ChiMuc"],
                        ten = chuong["TEN"],
                        stt = roman_to_int(chuong["ChiMuc"]),
                        demuc_id = filename.split(".")[0]
                    ))
                    inserted_chuong.add(chuong["MAPC"])
                except:
                    continue
            print(f'Inserted {len(chuongs_data)} chương của đề mục {filename.split(".")[0]}')

            with db.atomic():
                PDChuong.bulk_create(chuongs_data)

            #Tạo chương giả nếu không tồn tại chương
            if len(chuongs_data) == 0:
                chuong_data = PDChuong.create(
                    chuong_id = uuid.uuid4(),
                    chimuc = "0",
                    ten = "",
                    stt = 0,
                    demuc_id = filename.split(".")[0]
                )
                chuongs_data.append(chuong_data)

            print(f'Đề mục {filename.split(".")[0]} có {len(demuc_chuong)} chương và {len(demuc_dieu)} điều')

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
                    for chuong_data in chuongs_data:
                        if dieu["MAPC"].startswith(chuong_data.chuong_id):
                            chuong_id = chuong_data.chuong_id
                            break

                demuc_meta = demuc_dict.get(dieu["DeMucID"])
                if not demuc_meta:
                    print(f"Không tìm thấy đề mục cho điều {dieu['MAPC']}")
                    continue

                dieu_html = demuc_html.select(f'a[name="{dieu["MAPC"]}"]')[0]
                ten = dieu_html.next_sibling
                ghi_chu_html = dieu_html.parent.next_sibling
                vbqppl = ghi_chu_html.text if ghi_chu_html else None
                vbqppl_link = ghi_chu_html.select("a")[0]["href"] if ghi_chu_html and ghi_chu_html.select("a") else None
                noidung_html = dieu_html.parent.find_next("p", {"class": "pNoiDung"})
                noidung = ""

                for content in noidung_html.contents:
                    if content.name == "table":
                        tables.append(PDBang(dieu_id=dieu["MAPC"], html=str(content)))
                        continue
                    noidung += str(content.text.strip()) + "\n"
                try:
                    dieus_data.append(PDDieu(
                        dieu_id = dieu["MAPC"],
                        ten = dieu["TEN"],
                        stt = stt,
                        noi_dung = noidung,
                        chi_muc =  dieu["ChiMuc"],
                        ten_vbqppl = vbqppl,
                        link_vbqppl = vbqppl_link,
                        chuong_id = chuong_id,
                        demuc_id = dieu["DeMucID"],
                        chude_id = demuc_meta["ChuDe"]
                    ))
                    inserted_dieu.add(dieu["MAPC"])
                except Exception as e:
                    print(f'Lỗi insert điều {dieu["MAPC"]}: {e}')
                    continue
                element = noidung_html.next_sibling
                # Lấy link các file, biếu mẫu nếu có đính kèm
                while element and element.name == "a":

                    link = element["href"]
                    try:
                        files.append(PDFile(dieu_id=dieu["MAPC"], link=link, path=""))
                    except Exception as e:
                        print(f"Lỗi insert file {link}: {e}")

                    element = element.next_sibling
                # Lấy các điều có liên quan:

                if element and element.name == "p" and element["class"] and element["class"][0] == "pChiDan":
                    lienquans_html = element.select("a")
                    for lienquan_html in lienquans_html:
                        if not "onclick" in lienquan_html.attrs or lienquan_html["onclick"] == "":
                            continue
                        dieu_id_lienquan = extract_input(lienquan_html["onclick"]).replace("'", "")

                        dieus_lienquan.append({"dieu_id1": dieu["MAPC"], "dieu_id2": dieu_id_lienquan})

                stt += 1
            with db.atomic():
                PDDieu.bulk_create(dieus_data)
                PDBang.bulk_create(tables)
                PDFile.bulk_create(files)
            demuc_file.close()

dieus_lienquan_data = []

for dieu_lienquan in dieus_lienquan:
    if dieu_lienquan["dieu_id1"] not in inserted_dieu:
        print(f'{dieu_lienquan["dieu_id1"]} không tồn tại')
        continue
    if dieu_lienquan["dieu_id2"] not in inserted_dieu:
        print(f'{dieu_lienquan["dieu_id2"]} không tồn tại')
        continue
    try:
        dieus_lienquan_data.append(PDDieuLienQUan(
            dieu1 = dieu_lienquan["dieu_id1"],
            dieu2 = dieu_lienquan["dieu_id2"]
        ))
    except Exception as e:
        print(f'Không thể insert điều liên quan {dieu_lienquan["dieu_id1"]} - {dieu_lienquan["dieu_id2"]}: {e}')

with db.atomic():
    PDDieuLienQUan.bulk_create(dieus_lienquan_data)









