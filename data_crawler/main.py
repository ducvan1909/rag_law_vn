import json
import pathlib
import os
import uuid

from bs4 import BeautifulSoup
from db_config import db
from db_models.mysql_model import *
from utils import *

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

demuc_dir = pathlib.Path("./phap-dien/demuc")
dieus_lienquan = []

for file in os.listdir(demuc_dir):
    filename = os.fsdecode(file)
    if filename.endswith(".html"):
        filepath = os.path.join(demuc_dir, file)
        with open(filepath, "r", encoding="utf_8") as demuc_file:
            demuc_html = demuc_file.read()
            demuc_html = BeautifulSoup(demuc_html, "html.parser")
            demuc_node = [node for node in tree_nodes if node["DeMucID"] == filename.split(".")[0]]
            if len(demuc_node) == 0:
                print("Không tồn tại node cho đề mục:" + filename)
                demuc_file.close()
                continue
            demuc_chuong = [node for node in demuc_node if node["TEN"].startswith("Chương ")]

            #Insert Chương vào db
            chuongs_data = []
            for chuong in demuc_chuong:
                try:
                    chuong_data = PDChuong.create(
                        chuong_id = chuong["MAPC"],
                        chimuc = chuong["ChiMuc"],
                        ten = chuong["TEN"],
                        stt = roman_to_int(chuong["ChiMuc"]),
                        demuc_id = filename.split(".")[0]
                    )
                except:
                    continue
                chuongs_data.append(chuong_data)
            print(f'Inserted {len(chuongs_data)} chương của đề mục {filename.split(".")[0]}')

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

            demuc_dieu = [node for node in demuc_node if node["TEN"].startswith("Điều ")]

            print(f'Đề mục {filename.split(".")[0]} có {len(demuc_chuong)} chương và {len(demuc_dieu)} điều')

            stt = 0
            for dieu in demuc_dieu:
                if len(chuongs_data) == 1:
                    chuong_id = chuongs_data[0].chuong_id
                else:
                    for chuong_data in chuongs_data:
                        if dieu["MAPC"].startswith(chuong_data.chuong_id):
                            chuong_id = chuong_data.chuong_id
                            break

                demuc_db = PDDeMuc.get_or_none(PDDeMuc.demuc_id == dieu["DeMucID"])
                if not demuc_db:
                    print(f"Không tìm thấy đề mục cho điều {dieu['MAPC']}")
                    continue

                dieu_html = demuc_html.select(f'a[name="{dieu["MAPC"]}"]')[0]
                ten = dieu_html.next_sibling
                ghi_chu_html = dieu_html.parent.next_sibling
                vbqppl = ghi_chu_html.text if ghi_chu_html else None
                vbqppl_link = ghi_chu_html.select("a")[0]["href"] if ghi_chu_html and ghi_chu_html.select("a") else None
                noidung_html = dieu_html.parent.find_next("p", {"class": "pNoiDung"})
                noidung = ""
                tables = []
                for content in noidung_html.contents:
                    if content.name == "table":
                        tables.append(str(content))
                        continue
                    noidung += str(content.text.strip()) + "\n"
                try:
                    PDDieu.create(
                        dieu_id = dieu["MAPC"],
                        ten = dieu["TEN"],
                        stt = stt,
                        noi_dung = noidung,
                        chi_muc =  dieu["ChiMuc"],
                        ten_vbqppl = vbqppl,
                        link_vbqppl = vbqppl_link,
                        chuong_id = chuong_id,
                        demuc_id = dieu["DeMucID"],
                        chude_id = demuc_db.chude_id_id
                    )
                except Exception as e:
                    print(f'Lỗi insert điều {dieu["MAPC"]}: {e}')
                    continue

                for table in tables:
                    PDBang.create(dieu_id=dieu["MAPC"], html=table)

                element = noidung_html.next_sibling
                # Lấy link các file, biếu mẫu nếu có đính kèm
                while element and element.name == "a":

                    link = element["href"]
                    try:
                        PDFile.create(dieu_id=dieu["MAPC"], link=link, path="")
                    except:
                        print("Lỗi insert file" + link)

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
            demuc_file.close()

existing_dieu_ids = {row.dieu_id for row in PDDieu.select(PDDieu.dieu_id)}

for dieu_lienquan in dieus_lienquan:
    if dieu_lienquan["dieu_id2"] not in existing_dieu_ids:
        print(
            f'missing_target điều liên quan {dieu_lienquan["dieu_id1"]} - {dieu_lienquan["dieu_id2"]}'
        )
        continue
    try:
        PDDieuLienQUan.create(
            dieu1 = dieu_lienquan["dieu_id1"],
            dieu2 = dieu_lienquan["dieu_id2"]
        )
    except Exception as e:
        print(f'Không thể insert điều liên quan {dieu_lienquan["dieu_id1"]} - {dieu_lienquan["dieu_id2"]}: {e}')











