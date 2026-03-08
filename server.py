from fastapi import FastAPI, Request
from pydantic import BaseModel
import pymysql
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# 1. 모바일 및 외부 기기 접속 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB 연결 설정 ---
def get_db_connection():
    return pymysql.connect(
        host='127.0.0.1',
        user='root',
        password='root', 
        db='refrigerator_db',
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

class Item(BaseModel):
    name: str
    date: str

# --- 경로 설정 (Routes) ---

# A. 모바일용 웹 화면 (GET /)
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT name, date FROM items ORDER BY id DESC")
        items = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

# B. 데이터 저장 API (POST /items) - main.py에서 재료 추가 시 호출
@app.post("/items")
async def add_item(item: Item):
    conn = get_db_connection()
    with conn.cursor() as cursor:
        sql = "INSERT INTO items (name, date) VALUES (%s, %s)"
        cursor.execute(sql, (item.name, item.date))
    conn.commit()
    conn.close()
    return {"message": "저장 성공"}

# C. 데이터 조회 API (GET /items) - main.py에서 목록 새로고침 시 호출
@app.get("/items")
async def get_items():
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT name, date FROM items")
        result = cursor.fetchall()
    conn.close()
    return result

# 특정 이름을 가진 아이템을 삭제하는 로직
@app.delete("/items/{name}")
async def delete_item(name: str):
    conn = get_db_connection()
    with conn.cursor() as cursor:
        sql = "DELETE FROM items WHERE name = %s"
        cursor.execute(sql, (name,))
    conn.commit()
    conn.close()
    return {"message": f"{name} 삭제 성공"}