from fastapi import FastAPI, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timedelta
from typing import Optional, List
import database.models as models
from database.connection import get_db, engine, SessionLocal
from sqlalchemy.orm import joinedload
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from passlib.context import CryptContext
from api.items import get_current_user_id, get_optional_user_id
import re
import os
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# DB 테이블 생성
models.Base.metadata.create_all(bind=engine)

# [중요] 기본 재료 자동 충전기 (사전이 비어있을 때만 실행)
db_session = SessionLocal()
if db_session.query(models.MasterIngredient).count() == 0:
    default_ings = ["계란", "우유", "양파", "대파", "마늘", "돼지고기", "소고기", "김치", "당근", "사과", "두부", "버섯"]
    for ing in default_ings:
        db_session.add(models.MasterIngredient(name=ing))
    db_session.commit()
db_session.close()

app = FastAPI()

# 세팅 (Static & Templates)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- 메인 페이지 (냉장고 목록 및 D-Day 로직) ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    user_id = get_optional_user_id(request)
    items = []
    if user_id:
        # 사용자의 아이템 가져오기
        raw_items = db.query(models.UserIngredient).filter(models.UserIngredient.user_id == user_id).all()
        
        # D-Day 계산 로직 적용
        for item in raw_items:
            if item.expiry_date:
                delta = (item.expiry_date - datetime.now().date()).days
                item.d_day = delta
            else:
                item.d_day = None
            items.append(item)

    return templates.TemplateResponse("index.html", {"request": request, "items": items, "user_id": user_id})

# --- 영수증 스캔 API (네이버 CLOVA OCR 연동용) ---
@app.post("/scan-receipt")
async def scan_receipt(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return JSONResponse(content={"error": "로그인이 필요합니다."}, status_code=401)

    # 실제 OCR 연동 전까지 사용할 테스트용 목업 데이터
    # .env에 OCR_URL이 없을 경우 이 데이터가 들어갑니다.
    mock_ingredients = ["삼겹살", "대파", "깐마늘"]
    
    added_items = []
    for name in mock_ingredients:
        new_item = models.UserIngredient(
            user_id=user_id,
            name=name,
            expiry_date=datetime.now().date() + timedelta(days=7), # 기본 7일 부여
            category="기타"
        )
        db.add(new_item)
        added_items.append(name)
    
    db.commit()
    return {"message": "스캔 완료", "items": added_items}

# (이후 기존의 로그인/회원가입/재료추가 관련 API 코드들이 이어짐...)