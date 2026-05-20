import json
from db_config import db
from db_models.mysql_model import *

# Kết nối với database và tạo bảng
# db.connect(reuse_if_open=True)
# db.create_tables([PDChuDe, PDDeMuc, PDChuong, PDDieu, PDBang, PDFile, PDDieuLienQUan], safe=True)

print("Load các chủ đề")
with open("./phap-dien/chude.json", "r", encoding="utf_8") as f_chude:
    chudes = json.load(f_chude)
f_chude.close()

print("Insert các chủ đề")
try:
    with db.atomic():
        PDChuDe.bulk_create([PDChuDe(chude_id=chude["Value"], ten=chude["Text"], stt=chude["STT"]) for chude in chudes])
except:
    pass
print("Insert chủ đề thành công")

print("Load các đề mục")
with open("./phap-dien/demuc.json", "r", encoding="utf_8") as f_demuc:
    demucs = json.load(f_demuc)
f_demuc.close()

print("Insert các đề mục")
try:
    with db.atomic():
        PDDeMuc.bulk_create([PDDeMuc(demuc_id=demuc["Value"], chude_id=demuc["ChuDe"], ten=demuc["Text"], stt=demuc["STT"]) for demuc in demucs])
except:
    pass
print("Insert đề mục thành công")

print("Load tree nodes")
with open("./phap-dien/treeNode.json", "r", encoding="utf_8") as f_tree_nodes:
    tree_nodes = json.load(f_tree_nodes)
tree_nodes.close()

