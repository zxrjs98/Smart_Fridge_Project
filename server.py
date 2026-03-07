from fastapi import FastAPI
from pydantic import BaseModel
import pymysql
from typing import List

app = FastAPI()

# MySQL 접속 정보 (본인의 비밀번호로 수정하세요)
def get_db_connection():
    return pymysql.connect(
        host='127.0.0.1', # 'localhost' 대신 숫자로 써보세요 (더 안정적입니다)
        user='root',
        password='root', # <--- 이 부분이 틀리면 무한 로딩이 걸릴 수 있습니다
        db='refrigerator_db',
        charset='utf8mb4',
        connect_timeout=5, # 5초 안에 연결 안 되면 에러를 내도록 설정 (무한 로딩 방지)
        cursorclass=pymysql.cursors.DictCursor
    )

# 서버 시작 시 DB 및 테이블 자동 생성
def init_db():
    conn = pymysql.connect(host='localhost', user='root', password='root')
    cursor = conn.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS refrigerator_db")
    cursor.execute("USE refrigerator_db")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            date VARCHAR(50) NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

class Item(BaseModel):
    name: str
    date: str

@app.get("/items")
async def get_items():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT name, date FROM items")
        result = cursor.fetchall()
    conn.close()
    return result

@app.post("/items")
async def add_item(item: Item):
    conn = get_db_connection()
    with conn.cursor() as cursor:
        sql = "INSERT INTO items (name, date) VALUES (%s, %s)"
        cursor.execute(sql, (item.name, item.date))
    conn.commit()
    conn.close()
    return {"message": "MySQL 저장 성공"}