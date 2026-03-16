from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database.connection import engine, get_db, Base
from database.models import Item

# [추가] 분리한 API 라우터 가져오기
from api.items import router as items_router

app = FastAPI()
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# [핵심] 분리한 라우터 등록
app.include_router(items_router)

# 메인 페이지 렌더링만 남깁니다.
@app.get("/")
async def read_root(request: Request, db: Session = Depends(get_db)):
    items = db.query(Item).all()
    return templates.TemplateResponse("index.html", {"request": request, "items": items})