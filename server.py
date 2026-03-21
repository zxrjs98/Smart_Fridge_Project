from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database.connection import engine, get_db, Base
from database.models import Item
from api.items import router as items_router
from datetime import datetime

app = FastAPI()

# DB 테이블 생성
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# API 라우터 등록
app.include_router(items_router)

@app.get("/")
async def read_root(request: Request, db: Session = Depends(get_db)):
    # 유통기한 순으로 정렬해서 가져오면 더 보기 편합니다.
    items = db.query(Item).order_by(Item.expiry_date.asc()).all()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})

@app.get("/")
async def read_root(request: Request, db: Session = Depends(get_db)):
    items = db.query(Item).order_by(Item.expiry_date.asc()).all()
    
    # 각 아이템에 d_day 속성을 실시간으로 계산해서 넣어줍니다.
    today = datetime.now().date()
    for item in items:
        # item.expiry_date가 문자열이라면 날짜 객체로 변환 후 계산
        expiry = datetime.strptime(item.expiry_date, "%Y-%m-%d").date()
        item.d_day = (expiry - today).days 
        
    return templates.TemplateResponse("index.html", {"request": request, "items": items})