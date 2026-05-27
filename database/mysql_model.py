from peewee import *

from database.db_config import db

MAX_LENGTH = 128
UTF8MB4_UNICODE_TABLE_SETTINGS = (
    "CHARACTER SET utf8mb4",
    "COLLATE utf8mb4_unicode_ci",
)
UTF8MB4_AI_TABLE_SETTINGS = (
    "CHARACTER SET utf8mb4",
    "COLLATE utf8mb4_0900_ai_ci",
)


class LongTextField(TextField):
    field_type = "LONGTEXT"


class BaseModel(Model):
    class Meta:
        database = db


class PDChuDe(BaseModel):
    chude_id = CharField(max_length=MAX_LENGTH, primary_key=True)
    ten = TextField()
    stt = IntegerField()


class PDDeMuc(BaseModel):
    demuc_id = CharField(max_length=MAX_LENGTH, primary_key=True)
    ten = TextField()
    stt = IntegerField()
    chude_id = ForeignKeyField(PDChuDe, backref="demucs")


class PDChuong(BaseModel):
    chuong_id = CharField(max_length=MAX_LENGTH, primary_key=True)
    chimuc = TextField()
    ten = TextField()
    stt = IntegerField()
    demuc_id = ForeignKeyField(PDDeMuc, backref="chuongs")


class PDDieu(BaseModel):
    dieu_id = CharField(max_length=MAX_LENGTH, primary_key=True)
    ten = TextField()
    stt = IntegerField()
    noi_dung = TextField()
    chi_muc = IntegerField()
    ten_vbqppl = TextField()
    id_vbqppl = CharField(max_length=32, null=True)
    chuong_id = ForeignKeyField(PDChuong, backref="dieus")
    demuc_id = ForeignKeyField(PDDeMuc, backref="dieus")
    chude_id = ForeignKeyField(PDChuDe, backref="dieus")


class PDBang(BaseModel):
    dieu_id = ForeignKeyField(PDDieu, backref="bangs")
    html = TextField()


class PDFile(BaseModel):
    dieu_id = ForeignKeyField(PDDieu, backref="files")
    path = TextField()
    link = TextField()


class PDDieuLienQUan(BaseModel):
    dieu1 = ForeignKeyField(PDDieu)
    dieu2 = ForeignKeyField(PDDieu)


class VBPL(BaseModel):
    id = CharField(max_length=32, primary_key=True)
    html = LongTextField(null=True)
    status_name = CharField(max_length=255, null=True)

    class Meta:
        table_name = "vbpl"
        table_settings = UTF8MB4_UNICODE_TABLE_SETTINGS


class VBPLDocument(BaseModel):
    id = CharField(max_length=32, primary_key=True)
    plain_text = LongTextField(null=True)
    status_name = CharField(max_length=255, null=True)

    class Meta:
        table_name = "vbpl_document"
        table_settings = UTF8MB4_AI_TABLE_SETTINGS


class VBPLUnit(BaseModel):
    id = BigAutoField()
    document_id = ForeignKeyField(VBPLDocument, backref="units")
    dieu_id = ForeignKeyField(PDDieu, backref="vbpl_units")
    dieu = CharField(max_length=255)
    chuong = CharField(max_length=255)
    demuc = CharField(max_length=255)
    chude = CharField(max_length=255)
    ten_vbpl = TextField()
    content = LongTextField()
    char_start = IntegerField(null=True)
    char_end = IntegerField(null=True)
    status_name = CharField(max_length=255, null=True)

    class Meta:
        table_name = "vbpl_unit"
        table_settings = UTF8MB4_AI_TABLE_SETTINGS


STRUCTURE_TABLES = [
    PDChuDe,
    PDDeMuc,
    PDChuong,
    PDDieu,
    PDBang,
    PDFile,
    PDDieuLienQUan,
]
VBPL_TABLES = [VBPL]
VBPL_UNIT_TABLES = [VBPLDocument, VBPLUnit]
ALL_TABLES = STRUCTURE_TABLES + VBPL_TABLES + VBPL_UNIT_TABLES


def reset_tables(tables, drop_tables=None):
    tables_to_drop = drop_tables or tables
    db.drop_tables(list(reversed(tables_to_drop)), safe=True)
    db.create_tables(tables, safe=True)
