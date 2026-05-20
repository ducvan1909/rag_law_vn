import json
from db_config import db
from db_models.mysql_model import *

# Kết nối với database và tạo bảng
# db.connect(reuse_if_open=True)
# db.create_tables([PDChuDe, PDDeMuc, PDChuong, PDDieu, PDBang, PDFile, PDDieuLienQUan], safe=True)


with open("./phap-dien/chude.json", "r", encoding="utf_8") as f_chude:
    chude = json.load(f_chude)
f_chude.close()
print(type(chude))

print(chude[0])