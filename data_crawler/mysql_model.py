from peewee import *
from db_config import db

MAX_LENGTH = 128

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
    chude_id = ForeignKeyField(PDChuDe, backref='demucs')

class PDChuong(BaseModel):
    chuong_id = CharField(max_length=MAX_LENGTH, primary_key=True)
    chimuc = TextField()
    ten = TextField()
    stt = IntegerField()
    demuc_id = ForeignKeyField(PDDeMuc, backref='chuongs')

class PDDieu(BaseModel):
    dieu_id = CharField(max_length=MAX_LENGTH, primary_key=True)
    ten = TextField()
    stt = IntegerField()
    noi_dung = TextField()
    chi_muc = IntegerField()
    ten_vbqppl = TextField()
    id_vbqppl = CharField(max_length=32, null=True)
    chuong_id = ForeignKeyField(PDChuong, backref='dieus')
    demuc_id = ForeignKeyField(PDDeMuc, backref='dieus')
    chude_id = ForeignKeyField(PDChuDe, backref='dieus')

class PDBang(BaseModel):
    dieu_id = ForeignKeyField(PDDieu, backref='bangs')
    html = TextField()

class PDFile(BaseModel):
    dieu_id = ForeignKeyField(PDDieu, backref='files')
    path = TextField()
    link = TextField()

class PDDieuLienQUan(BaseModel):
    dieu1 = ForeignKeyField(PDDieu)
    dieu2 = ForeignKeyField(PDDieu)
