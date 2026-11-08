# ==========================================
# 📦 기본 패키지 및 도구 모음
# ==========================================
import os
import re
import smtplib
import string
import random
import time
import uuid
import json
import difflib
from typing import Optional, List
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel
from typing import List

# ==========================================
# 🚀 FastAPI 관련 도구
# ==========================================
from fastapi import FastAPI, Depends, HTTPException, Request, Form, UploadFile, File, Path
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi import Body, HTTPException

# ==========================================
# 💾 데이터베이스 및 기능 도구
# ==========================================
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from database.connection import engine, get_db
import database.models as models
from passlib.context import CryptContext
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from pywebpush import webpush, WebPushException
import requests
from openai import OpenAI

# 🔐 쿠키 서명(위조 방지)
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# 환경 변수 로드
load_dotenv()

app = FastAPI()

# DB 테이블 자동 생성
models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# -----------------------------
# 🔐 세션 쿠키 서명/검증 헬퍼
# -----------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(".env 파일에 SECRET_KEY를 추가해주세요! (예: python -c \"import secrets; print(secrets.token_hex(32))\")")

serializer = URLSafeTimedSerializer(SECRET_KEY)
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30일

def create_session_cookie(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})

def get_current_user_id(request: Request) -> Optional[int]:
    """서명된 쿠키를 검증해서 user_id를 반환. 위조/만료/없음이면 None."""
    token = request.cookies.get("user_id")
    if not token:
        return None
    try:
        data = serializer.loads(token, max_age=COOKIE_MAX_AGE)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None

def set_login_cookie(response, user_id: int):
    response.set_cookie(
        key="user_id",
        value=create_session_cookie(user_id),
        httponly=True,
        max_age=COOKIE_MAX_AGE,
        samesite="lax"
    )

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    return pwd_context.hash(pwd_bytes)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# -----------------------------
# 💡 이메일 발송 도우미 함수
# -----------------------------
def send_temp_password(receiver_email, temp_pw):
    sender_email = os.getenv("EMAIL_SENDER")
    sender_pw = os.getenv("EMAIL_PASSWORD")
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "[FreshKeep] 임시 비밀번호가 발급되었습니다."
    body = f"안녕하세요!\n요청하신 임시 비밀번호는 [{temp_pw}] 입니다.\n로그인 후 마이페이지에서 반드시 비밀번호를 변경해주세요."
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_pw)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"메일 발송 에러: {e}")
        return False

def send_id_email(receiver_email, username):
    sender_email = os.getenv("EMAIL_SENDER")
    sender_pw = os.getenv("EMAIL_PASSWORD")
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "[FreshKeep] 요청하신 아이디 정보입니다."
    body = f"안녕하세요!\n회원님의 가입 아이디는 [ {username} ] 입니다.\n로그인 후 서비스를 이용해주세요."
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_pw)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"메일 발송 에러: {e}")
        return False

# ---------------------------------------------------------
# 1. 인증 및 계정 관리 (Login / Register / Profile)
# ---------------------------------------------------------
@app.get("/")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login_user(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "아이디 또는 비밀번호가 일치하지 않습니다."})
    
    response = RedirectResponse(url="/main", status_code=303)
    set_login_cookie(response, user.id)
    return response

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")   

@app.post("/register")
def register_user(request: Request, username: str = Form(default=""), password: str = Form(default=""), password_confirm: str = Form(default=""), email: str = Form(...), db: Session = Depends(get_db)):
    errors = {} 
    if not (6 <= len(username) <= 12):
        errors["username_error"] = "아이디는 6~12글자로 해주세요."
    elif db.query(models.User).filter(models.User.username == username).first():
        errors["username_error"] = "이미 존재하는 아이디입니다."

    if not (8 <= len(password) <= 14):
        errors["password_error"] = "비밀번호는 8~14글자로 해주세요."
    else:
        has_letter = any(c.isalpha() for c in password)
        has_number = any(c.isdigit() for c in password)
        has_special = any(not c.isalnum() for c in password)
        if (has_letter + has_number + has_special) < 2:
            errors["password_error"] = "영문, 숫자, 특수문자 중 2가지 이상을 조합해주세요."

    if password != password_confirm:
        errors["confirm_error"] = "비밀번호가 일치하지 않습니다."

    email_regex = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    if not email_regex.match(email):
        errors["email_error"] = "올바른 이메일 형식을 입력해주세요."
    elif db.query(models.User).filter(models.User.email == email).first():
        errors["email_error"] = "이미 가입된 이메일입니다."

    if errors:
        return templates.TemplateResponse(request=request, name="register.html", context={"errors": errors, "username": username, "email": email})

    new_user = models.User(username=username, hashed_password=get_password_hash(password), email=email)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id", path="/")
    return response

@app.post("/withdraw")
def withdraw_account(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    db.delete(user)
    db.commit()
    response = HTMLResponse("<script>alert('회원 탈퇴가 완료되었습니다. 그동안 이용해주셔서 감사합니다.'); window.location.href='/';</script>")
    response.delete_cookie("user_id")
    return response

@app.get("/find-id", response_class=HTMLResponse)
async def get_find_id_page(request: Request):
    return templates.TemplateResponse(request=request, name="find-id.html")

@app.post("/find-id")
async def find_id(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        send_id_email(user.email, user.username)
        return templates.TemplateResponse(request=request, name="find-id.html", context={"email_sent": True, "sent_email": email})
    else:
        return templates.TemplateResponse(request=request, name="find-id.html", context={"input_email": email, "id_error": "가입된 이메일이 없습니다."})

@app.get("/find-pw", response_class=HTMLResponse)
async def get_find_pw_page(request: Request):
    return templates.TemplateResponse(request=request, name="find-pw.html")

@app.post("/find-pw")
async def find_pw(request: Request, username: str = Form(...), email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username, models.User.email == email).first()
    if user:
        temp_pw = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        hashed_pw = pwd_context.hash(temp_pw)
        db.query(models.User).filter(models.User.username == username).update({"hashed_password": hashed_pw})
        db.commit()
        send_temp_password(user.email, temp_pw)
        return templates.TemplateResponse(request=request, name="find-pw.html", context={"pw_message": "입력하신 이메일로 임시 비밀번호를 발송했습니다.", "success": True})
    else:
        return templates.TemplateResponse(request=request, name="find-pw.html", context={"pw_error": "아이디와 일치하는 이메일이 없습니다."})

@app.get("/profile")
def profile_page(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return templates.TemplateResponse(request=request, name="profile.html", context={"user": user})

@app.post("/update-profile")
def update_profile(current_pw: str = Form(None), new_pw: str = Form(None), new_pw_confirm: str = Form(None), db: Session = Depends(get_db), request: Request = None):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if current_pw and new_pw and new_pw_confirm:
        if not verify_password(current_pw, user.hashed_password):
            return JSONResponse({"status": "error", "message": "현재 비밀번호가 틀렸습니다."})
        if new_pw != new_pw_confirm:
            return JSONResponse({"status": "error", "message": "새 비밀번호가 일치하지 않습니다."})
        if not (8 <= len(new_pw) <= 14):
            return JSONResponse({"status": "error", "message": "비밀번호는 8~14글자로 해주세요."})
        
        user.hashed_password = get_password_hash(new_pw)
        db.commit()
        return JSONResponse({"status": "success"})
    return JSONResponse({"status": "error", "message": "모든 필드를 입력해주세요."})

# ---------------------------------------------------------
# 2. 메인 서비스 (냉장고 관리)
# ---------------------------------------------------------
@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/", status_code=303)

    try:
        staples = get_user_staples(db, user_id)
        items = db.query(models.Item).filter(models.Item.user_id == user_id).order_by(models.Item.expiry_date.is_(None), models.Item.expiry_date.asc()).all()
        today = date.today()
        processed_items = []
        for item in items:
            if item.name in staples:
                continue  # 기본 재료는 냉장고 목록에서 숨김
            d_day = (item.expiry_date - today).days if item.expiry_date else None
            processed_items.append({"id": item.id, "name": item.name, "expiry_date": item.expiry_date, "d_day": d_day})

        response = templates.TemplateResponse(request=request, name="index.html", context={"items": processed_items, "current_user": user_id, "staples": sorted(staples)})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    
    except Exception as e:
        response = templates.TemplateResponse(request=request, name="index.html", context={"items": [], "error": str(e)})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    

@app.get("/items/search")
def search_ingredients(q: str = "", db: Session = Depends(get_db)):
    query = db.query(models.MasterIngredient)
    if not q or q == "popular":
        results = query.order_by(models.MasterIngredient.name.asc()).limit(100).all()
    else:
        results = query.filter(models.MasterIngredient.name.contains(q)).all()
    return [{"name": r.name, "is_seasoning": r.is_seasoning} for r in results]

@app.post("/items")
async def create_item(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    data = await request.json()
    expiry_str = data.get('expiry_date')
    expiry = datetime.strptime(expiry_str, '%Y-%m-%d').date() if expiry_str and expiry_str.strip() else None
    new_item = models.Item(name=data['name'], expiry_date=expiry, user_id=user_id)
    db.add(new_item)
    db.commit()
    return {"message": "success"}

@app.post("/update-item/{item_id}")
async def update_item_date(
    item_id: int,
    request: Request,
    body: dict = Body(...),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    new_date_str = body.get("expiry_date")
    new_date = None
    if new_date_str:
        new_date = datetime.strptime(new_date_str, "%Y-%m-%d").date()

    item = db.query(models.Item).filter(models.Item.id == item_id, models.Item.user_id == user_id).first()
    
    if item:
        item.expiry_date = new_date
        db.commit()
        return {"status": "success"}
        
    raise HTTPException(status_code=404, detail="해당 재료를 찾을 수 없습니다.")

@app.delete("/items/{item_id}")
def delete_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    item = db.query(models.Item).filter(models.Item.id == item_id, models.Item.user_id == user_id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404)

# ---------------------------------------------------------
# 3. 마이페이지 및 장보기 목록
# ---------------------------------------------------------
@app.get("/mypage", response_class=HTMLResponse)
async def get_menu_page(request: Request):
    return templates.TemplateResponse(request=request, name="mypage.html")

@app.get("/shopping")
def get_shopping_list(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
    shopping_list = db.query(models.ShoppingList).filter(models.ShoppingList.user_id == user_id).all()
    return templates.TemplateResponse(request=request, name="shopping.html", context={"items": shopping_list})

@app.post("/shopping/add")
def add_shopping_item(request: Request, item_name: str = Form(...), db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return {"error": "로그인이 필요합니다."}
    existing_item = db.query(models.ShoppingList).filter(models.ShoppingList.user_id == user_id, models.ShoppingList.item_name == item_name).first()
    if existing_item:
        return RedirectResponse(url="/shopping", status_code=303)
    new_item = models.ShoppingList(item_name=item_name, user_id=user_id, is_bought=False)
    db.add(new_item)
    db.commit()
    return RedirectResponse(url="/shopping", status_code=303)

@app.post("/shopping/delete/{item_id}")
def delete_shopping_item(request: Request, item_id: int = Path(...), db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
    item_to_delete = db.query(models.ShoppingList).filter(models.ShoppingList.id == item_id, models.ShoppingList.user_id == user_id).first()
    if not item_to_delete:
        return {"error": "삭제 권한이 없거나 존재하지 않는 항목입니다."}
    db.delete(item_to_delete)
    db.commit()
    return RedirectResponse(url="/shopping", status_code=303)

# 기본 재료 초기값 - 실제 레시피 재료명과 일치해야 효과가 있어요 (아래 SQL로 확인)
DEFAULT_STAPLES = ["소금", "설탕", "후추", "간장", "참기름", "식용유", "고춧가루", "다진마늘", "물"]

def get_user_staples(db: Session, user_id: int) -> set:
    """기본값 + 사용자가 추가한 것 - 사용자가 제거한 것"""
    staples = set(DEFAULT_STAPLES)
    for row in db.query(models.UserStaple).filter(models.UserStaple.user_id == user_id).all():
        if row.is_staple:
            staples.add(row.ingredient_name)
        else:
            staples.discard(row.ingredient_name)
    return staples

class StapleRequest(BaseModel):
    name: str

@app.get("/api/staples")
def get_staples(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return {"staples": sorted(get_user_staples(db, user_id))}

@app.post("/api/staples")
def add_staple(body: StapleRequest, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    name = body.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="잘못된 재료명입니다.")

    row = db.query(models.UserStaple).filter(
        models.UserStaple.user_id == user_id, models.UserStaple.ingredient_name == name
    ).first()
    if name in DEFAULT_STAPLES:
        if row:
            db.delete(row)  # "제거함" 표시를 지우면 기본값으로 복구
    elif row:
        row.is_staple = True
    else:
        db.add(models.UserStaple(user_id=user_id, ingredient_name=name, is_staple=True))
    db.commit()
    return {"status": "success"}

@app.delete("/api/staples")
def remove_staple(name: str, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    name = name.strip()

    row = db.query(models.UserStaple).filter(
        models.UserStaple.user_id == user_id, models.UserStaple.ingredient_name == name
    ).first()
    if name in DEFAULT_STAPLES:
        if row:
            row.is_staple = False
        else:
            db.add(models.UserStaple(user_id=user_id, ingredient_name=name, is_staple=False))
    elif row:
        db.delete(row)
    db.commit()
    return {"status": "success"}

# ---------------------------------------------------------
# 4. 레시피 및 OCR 스캔 연동
# ---------------------------------------------------------
@app.get("/api/recipes")
def get_recipes(request: Request, db: Session = Depends(get_db)):
    current_user_id = get_current_user_id(request)

    all_raw_recipes = db.query(models.Recipe).all()
    favorite_ids = set()
    usage_counts = {}
    staples = set()
    if current_user_id:
        favs = db.query(models.Favorite.recipe_id).filter(models.Favorite.user_id == current_user_id).all()
        favorite_ids = {f[0] for f in favs}

        counts = db.query(models.MealLog.recipe_id, func.count(models.MealLog.id)).filter(
            models.MealLog.user_id == current_user_id
        ).group_by(models.MealLog.recipe_id).all()
        usage_counts = {rid: cnt for rid, cnt in counts}

        staples = get_user_staples(db, current_user_id)

    results = []
    for r in all_raw_recipes:
        rid = getattr(r, 'recipe_id', None) or getattr(r, 'id', None)
        ings = db.query(models.RecipeIngredient.ingredient_name).filter(models.RecipeIngredient.recipe_id == rid).all()
        ing_names = [i[0] for i in ings]
        visible_ings = [n for n in ing_names if n not in staples]
        staple_ings = [n for n in ing_names if n in staples]
        if not visible_ings:  # 전부 기본 재료면 0으로 나누기 방지를 위해 원본 유지
            visible_ings, staple_ings = ing_names, []
        results.append({
            "id": rid, "name": r.name, "ingredients": visible_ings,
            "staple_ingredients": staple_ings,
            "favorite": rid in favorite_ids, "image_url": r.image_url or "",
            "instructions": r.instructions or "", "original_ingredients": r.original_ingredients or "",
            "used_count": usage_counts.get(rid, 0)
        })
    return results

def urgency_weight(d_day):
    """남은 일수 -> 긴급도 점수. 만료(음수)는 먹도록 유도하면 안 되므로 0점."""
    if d_day is None or d_day < 0:
        return 0
    if d_day <= 1:
        return 4
    if d_day <= 3:
        return 3
    if d_day <= 7:
        return 1
    return 0

@app.get("/api/recipes/recommend")
def recommend_recipes(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    today = date.today()
    fridge_items = db.query(models.Item).filter(models.Item.user_id == user_id).all()

    staples = get_user_staples(db, user_id)
    my_ing_names = set()
    ing_dday = {}  # 재료명 -> 가장 급한 D-day
    for item in fridge_items:
        d = (item.expiry_date - today).days if item.expiry_date else None
        if d is not None and d < 0:
            continue  # 만료된 재료는 보유 재료로 치지 않음
        my_ing_names.add(item.name)
        if d is not None and (item.name not in ing_dday or d < ing_dday[item.name]):
            ing_dday[item.name] = d

    # 레시피 재료를 한 번에 조회 (레시피마다 쿼리하지 않도록)
    recipe_ings = {}
    rows = db.query(models.RecipeIngredient.recipe_id, models.RecipeIngredient.ingredient_name).all()
    for rid, name in rows:
        lst = recipe_ings.setdefault(rid, [])
        if name not in lst:
            lst.append(name)

    scored = []
    for r in db.query(models.Recipe).all():
        all_ings = recipe_ings.get(r.recipe_id, [])
        ings = [i for i in all_ings if i not in staples]
        staple_ings = [i for i in all_ings if i in staples]
        if not ings:
            continue

        have = [i for i in ings if i in my_ing_names]
        urgent = [(i, ing_dday[i]) for i in have if urgency_weight(ing_dday.get(i)) > 0]
        if not urgent:
            continue  # 임박 재료를 하나도 안 쓰면 추천 대상 아님

        urgent.sort(key=lambda x: x[1])
        scored.append({
            "id": r.recipe_id,
            "name": r.name,
            "image_url": r.image_url or "",
            "ingredients": ings,
            "match_rate": round(len(have) / len(ings) * 100),
            "staple_ingredients": staple_ings,
            "urgency_score": sum(urgency_weight(d) for _, d in urgent),
            "urgent_items": [{"name": n, "d_day": d} for n, d in urgent]
        })

    # 임박도 점수 높은 순, 동점이면 보유율 높은 순
    scored.sort(key=lambda x: (-x["urgency_score"], -x["match_rate"]))
    return scored[:3]

@app.post("/api/recipes/{recipe_id}/favorite")
async def toggle_favorite(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    data = await request.json()
    fav_record = db.query(models.Favorite).filter(models.Favorite.user_id == user_id, models.Favorite.recipe_id == recipe_id).first()
    if data.get("favorite") and not fav_record:
        db.add(models.Favorite(user_id=user_id, recipe_id=recipe_id))
    elif not data.get("favorite") and fav_record:
        db.delete(fav_record)
    db.commit()
    return {"message": "success"}

@app.get("/api/recipes/{recipe_id}/match-items")
def match_recipe_items(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    recipe_ingredients = db.query(models.RecipeIngredient.ingredient_name).filter(
        models.RecipeIngredient.recipe_id == recipe_id
    ).all()
    staples = get_user_staples(db, user_id)
    ingredient_names = [i[0] for i in recipe_ingredients if i[0] not in staples]

    fridge_items = db.query(models.Item).filter(models.Item.user_id == user_id).all()

    matched = []
    used_item_ids = set()
    for ing_name in ingredient_names:
        # 1순위: 이름이 정확히 일치하는 재료
        exact = [it for it in fridge_items if it.name == ing_name and it.id not in used_item_ids]
        item = exact[0] if exact else None

        # 2순위: 유사한 이름으로 퍼지 매칭 (예: "대파" ~ "쪽파")
        if not item:
            candidates = {it.name: it for it in fridge_items if it.id not in used_item_ids}
            close = difflib.get_close_matches(ing_name, candidates.keys(), n=1, cutoff=0.6)
            item = candidates[close[0]] if close else None

        if item:
            used_item_ids.add(item.id)
            matched.append({"ingredient_name": ing_name, "item_id": item.id, "item_name": item.name})
        else:
            matched.append({"ingredient_name": ing_name, "item_id": None, "item_name": None})

    return {"matched": matched}

class ConsumeRequest(BaseModel):
    recipe_id: int
    recipe_name: str
    consumed_item_ids: List[int] = []   # 사용자가 "다 썼어요" 체크한 Item.id 목록

@app.post("/api/recipes/consume")
async def consume_recipe(request: Request, body: ConsumeRequest, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    deleted_names = []
    if body.consumed_item_ids:
        items_to_delete = db.query(models.Item).filter(
            models.Item.id.in_(body.consumed_item_ids),
            models.Item.user_id == user_id
        ).all()
        for item in items_to_delete:
            deleted_names.append(item.name)
            db.delete(item)

    new_log = models.MealLog(
        user_id=user_id,
        recipe_id=body.recipe_id,
        recipe_name=body.recipe_name,
        consumed_items=json.dumps(deleted_names, ensure_ascii=False)
    )
    db.add(new_log)
    db.commit()

    return {"status": "success", "deleted_items": deleted_names}

@app.get("/api/meal-logs")
def get_meal_logs(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401)

    logs = db.query(models.MealLog).filter(
        models.MealLog.user_id == user_id
    ).order_by(models.MealLog.consumed_at.desc()).all()

    return [
        {
            "recipe_name": log.recipe_name,
            "consumed_at": log.consumed_at.strftime("%Y-%m-%d %H:%M"),
            "consumed_items": json.loads(log.consumed_items) if log.consumed_items else []
        }
        for log in logs
    ]

@app.delete("/api/meal-logs")
def delete_meal_logs(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401)
    db.query(models.MealLog).filter(models.MealLog.user_id == user_id).delete()
    db.commit()
    return {"status": "success"}

# 네이버 OCR 통신 코드

import json
from openai import OpenAI

@app.post("/scan_receipt")
async def scan_receipt(
    request: Request,
    receipt: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    invoke_url = os.getenv("OCR_INVOKE_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not invoke_url or not secret_key or not openai_api_key:
        raise HTTPException(status_code=500, detail=".env의 OCR/OpenAI API 설정을 확인해주세요.")

    try:
        # 1. 네이버 CLOVA OCR: 영수증 상품명 추출
        image_bytes = await receipt.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="영수증 이미지가 비어 있습니다.")
        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="10MB 이하의 이미지를 올려주세요.")

        filename = receipt.filename or "receipt.png"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        if ext not in {"png", "jpg", "jpeg"}:
            raise HTTPException(status_code=400, detail="PNG 또는 JPG 영수증 이미지를 사용해주세요.")

        request_json = {
            "images": [{"format": ext, "name": "receipt_scan"}],
            "requestId": str(uuid.uuid4()),
            "version": "V2",
            "timestamp": int(time.time() * 1000),
            "receipt": {"enable": True}
        }
        response = requests.post(
            invoke_url,
            headers={"X-OCR-SECRET": secret_key},
            data={"message": json.dumps(request_json).encode("utf-8")},
            files=[("file", (filename, image_bytes, receipt.content_type or "image/png"))],
            timeout=45
        )
        response.raise_for_status()
        ocr_result = response.json()

        raw_items = []
        for image in ocr_result.get("images", []):
            receipt_info = image.get("receipt", {}).get("result", {})
            for sub_result in receipt_info.get("subResults", []):
                for item in sub_result.get("items", []):
                    raw_name = item.get("name", {}).get("text", "")
                    if isinstance(raw_name, str) and raw_name.strip():
                        raw_items.append(raw_name.strip())

        if not raw_items:
            return {"status": "success", "items": [], "ingredient_names": []}

        # 2. 653개 표준 재료명은 기존 master_ingredients를 기준으로 사용
        valid_names = {
            row[0] for row in db.query(models.MasterIngredient.name).all()
            if row[0]
        }
        if not valid_names:
            raise HTTPException(status_code=500, detail="표준 재료 사전이 비어 있습니다.")

        # 3. 영수증 상품명 오타 보정 + 표준 재료명 매칭 (기존 한 번의 요청으로 처리)
        system_prompt = """
        너는 영수증에 인쇄된 상품명을 읽기 쉬운 이름으로 보정하고, 재료 사전과 연결하는 도우미야.

        [상품명 보정]
        1. 입력 상품마다 결과 1개를 작성하고 index를 정확히 보존한다.
        2. corrected에는 확신할 수 있는 인식 오타, 기호, 띄어쓰기만 수정한다.
        3. 상품 종류가 불확실하면 특정 종류를 추측해 확정하지 않는다.
        예: '검은쿵무유'는 검은콩 음료일 가능성이 있지만 두유/우유 여부는 불명확하다.
        4. 원래 브랜드, 부위, 식품의 정체는 가능한 한 유지한다.

        [표준 재료명 매칭]
        5. matched는 반드시 제공된 표준 재료명 목록 중 하나 또는 null이어야 한다.
        6. 돼지 목심, 돼지 삼겹 등은 더 구체적인 이름이 목록에 없다면
        요리 재료의 공통 범주인 '돼지고기'로 연결해도 된다.
        7. '복분자 막걸리'를 '복분자'로, '검은콩 음료'를 '검은콩'으로 연결하지 않는다.
        이런 경우 적절한 음료명이 목록에 없으면 matched는 null이다.
        8. 다른 상품을 하나로 합치거나 누락하지 않는다.

        반드시 다음 JSON 객체 형태로만 대답한다.
        {"items": [
        {"index": 0, "corrected": "국내산 생강", "matched": "생강"},
        {"index": 1, "corrected": null, "matched": null}
        ]}
        """

        indexed_items = [
            {"index": i, "original": name}
            for i, name in enumerate(raw_items)
        ]
        client = OpenAI(api_key=openai_api_key)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        "표준 재료명 목록:\n"
                        + json.dumps(sorted(valid_names), ensure_ascii=False)
                        + "\n영수증 상품들:\n"
                        + json.dumps(indexed_items, ensure_ascii=False)
                    )
                }
            ],
            response_format={"type": "json_object"}
        )
        parsed = json.loads(completion.choices[0].message.content)

        # 결과가 일부 누락되어도 원본 1:1 목록을 지킵니다.
        corrected_by_index = [None] * len(raw_items)
        matched_by_index = [None] * len(raw_items)

        for entry in parsed.get("items", []):
            if not isinstance(entry, dict):
                continue
            index = entry.get("index")
            if type(index) is not int or not (0 <= index < len(raw_items)):
                continue

            corrected = entry.get("corrected")
            matched = entry.get("matched")
            if isinstance(corrected, str) and corrected.strip():
                corrected_by_index[index] = corrected.strip()
            if isinstance(matched, str) and matched.strip() in valid_names:
                matched_by_index[index] = matched.strip()

        # 확실하지 않은 오분류를 막고, 기존의 돼지고기 매칭은 유지한다.
        # 이 규칙은 관찰된 사례에 대한 최소한의 보정이며, 전체 상품명을 해결하지는 않는다.
        for i, raw in enumerate(raw_items):
            corrected = corrected_by_index[i] or raw
            matched = matched_by_index[i]

            # 음료를 구성 원재료로 잘못 저장하지 않는다.
            if "막걸리" in raw and matched == "복분자":
                matched_by_index[i] = None

            # '무유'는 우유와 두유 중 어느 쪽인지 불명확한 오인식.
            if "검은쿵무유" in raw.replace(" ", "") or (
                "검은콩" in corrected and "무유" in corrected
            ):
                corrected_by_index[i] = corrected.replace("검은쿵", "검은콩").replace(
                    "무유", "음료 (종류 확인 필요)"
                )
                if matched in {"검은콩", "콩"}:
                    matched_by_index[i] = None

            # 돼지 목심/삼겹 부위는 레시피 DB에서 허용하는 상위 분류로 연결.
            if (matched_by_index[i] is None and "돼지고기" in valid_names
                    and "돼지" in raw and any(k in raw for k in ("목심", "목살", "삼겹"))):
                matched_by_index[i] = "돼지고기"

        results = [
            {
                "original": raw,
                "corrected": corrected_by_index[i],
                "matched": matched_by_index[i]
            }
            for i, raw in enumerate(raw_items)
        ]
        print("OCR 인식 결과:", raw_items)
        print("상품명 보정 및 재료 매칭:", results)

        # 중요: 여기서는 db.add/db.commit을 수행하지 않습니다.
        return {
            "status": "success",
            "items": results,
            "ingredient_names": sorted(valid_names)
        }

    except HTTPException:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": "영수증 분석 중 오류가 발생했습니다. 서버 로그를 확인해주세요."}


@app.post("/scan_receipt/save")
async def save_scanned_receipt_items(
    request: Request,
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    payload = await request.json()
    entries = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise HTTPException(status_code=400, detail="저장할 재료를 1~100개 선택해주세요.")

    valid_names = {
        row[0] for row in db.query(models.MasterIngredient.name).all()
    }
    staples = get_user_staples(db, user_id)
    checked = []
    skipped = 0

    # 일부 항목이 잘못되면 DB에 아무것도 저장하지 않도록 먼저 모두 검증합니다.
    for entry in entries:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="잘못된 재료 데이터입니다.")
        name = entry.get("name")
        expiry_text = entry.get("expiry_date") or ""
        if not isinstance(name, str):
            raise HTTPException(status_code=400, detail="재료명 형식이 올바르지 않습니다.")
        name = name.strip()
        if name not in valid_names:
            raise HTTPException(status_code=400, detail=f"표준 재료 사전에 없는 재료입니다: {name}")
        if name in staples:
            skipped += 1
            continue  # 기존 코드와 동일: 기본 재료는 별도 저장하지 않음

        if not isinstance(expiry_text, str):
            raise HTTPException(status_code=400, detail="소비기한 형식이 올바르지 않습니다.")
        try:
            expiry_date = datetime.strptime(expiry_text, "%Y-%m-%d").date() if expiry_text else None
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{name}의 소비기한이 올바르지 않습니다.")
        checked.append(models.Item(name=name, expiry_date=expiry_date, user_id=user_id))

    try:
        db.add_all(checked)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"status": "success", "saved_count": len(checked), "skipped_count": skipped}



@app.post("/scan_receipt/save")
async def save_scanned_receipt_items(
    request: Request,
    db: Session = Depends(get_db)
):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    payload = await request.json()
    entries = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(entries, list) or not 1 <= len(entries) <= 100:
        raise HTTPException(status_code=400, detail="저장할 재료를 1~100개 선택해주세요.")

    valid_names = {
        row[0] for row in db.query(models.MasterIngredient.name).all()
    }
    staples = get_user_staples(db, user_id)
    checked = []
    skipped = 0

    # 일부 항목이 잘못되면 DB에 아무것도 저장하지 않도록 먼저 모두 검증합니다.
    for entry in entries:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="잘못된 재료 데이터입니다.")
        name = entry.get("name")
        expiry_text = entry.get("expiry_date") or ""
        if not isinstance(name, str):
            raise HTTPException(status_code=400, detail="재료명 형식이 올바르지 않습니다.")
        name = name.strip()
        if name not in valid_names:
            raise HTTPException(status_code=400, detail=f"표준 재료 사전에 없는 재료입니다: {name}")
        if name in staples:
            skipped += 1
            continue  # 기존 코드와 동일: 기본 재료는 별도 저장하지 않음

        if not isinstance(expiry_text, str):
            raise HTTPException(status_code=400, detail="소비기한 형식이 올바르지 않습니다.")
        try:
            expiry_date = datetime.strptime(expiry_text, "%Y-%m-%d").date() if expiry_text else None
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{name}의 소비기한이 올바르지 않습니다.")
        checked.append(models.Item(name=name, expiry_date=expiry_date, user_id=user_id))

    try:
        db.add_all(checked)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"status": "success", "saved_count": len(checked), "skipped_count": skipped}


# ---------------------------------------------------------
# 5. 웹 푸시 알림 및 스케줄러 시스템
# ---------------------------------------------------------
@app.get("/sw.js")
def get_service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")

@app.get("/api/notifications/check")
def check_notifications(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401)
    
    today = date.today()
    items = db.query(models.Item).filter(models.Item.user_id == user_id).all()
    
    urgent_list = []
    for item in items:
        if item.expiry_date:
            d_day = (item.expiry_date - today).days
            if d_day in [1, 3]:
                urgent_list.append({"name": item.name, "d_day": d_day})
    if urgent_list:
        return {"has_urgent": True, "items": urgent_list}
    return {"has_urgent": False, "items": []}

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")

@app.get("/api/vapid-public-key")
def get_vapid_public_key():
    return {"public_key": VAPID_PUBLIC_KEY}

@app.post("/api/notifications/subscribe")
async def subscribe_notifications(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401)
    
    subscription_info = await request.json()
    existing = db.query(models.PushSubscription).filter(models.PushSubscription.user_id == user_id).first()
    if existing:
        existing.subscription_info = json.dumps(subscription_info)
    else:
        new_sub = models.PushSubscription(user_id=user_id, subscription_info=json.dumps(subscription_info))
        db.add(new_sub)
    db.commit()
    return {"status": "success"}

def check_expiry_and_queue_notifications():
    db: Session = next(get_db())
    try:
        now = datetime.now().strftime("%H:%M")
        today = date.today()
        users = db.query(models.User).filter(models.User.notification_time == now).all()

        for user in users:
            staples = get_user_staples(db, user.id)
            items = db.query(models.Item).filter(models.Item.user_id == user.id, models.Item.expiry_date.isnot(None)).all()
            urgent_items = []
            for item in items:
                if item.name in staples:
                    continue
                d_day = (item.expiry_date - today).days
                if d_day in [0, 1, 2, 3]:
                    urgent_items.append(f"{item.name}(D-{d_day})" if d_day != 0 else f"{item.name}(D-Day)")

            if not urgent_items:
                continue

            push_sub = db.query(models.PushSubscription).filter(models.PushSubscription.user_id == user.id).first()
            if push_sub:
                sub_info = json.loads(push_sub.subscription_info)
                try:
                    webpush(
                        subscription_info=sub_info,
                        data=json.dumps({"title": "FreshKeep 소비기한 알림", "body": f"임박 재료: {', '.join(urgent_items)}"}),
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": "mailto:hsh021215@gmail.com"}
                    )
                    print(f"유저 {user.id} 푸시 발송 성공")
                except WebPushException as ex:
                    print(f"푸시 발송 실패: {ex}")
    finally:
        db.close()

@app.post("/api/notification-time")
async def update_notification_time(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401)
    data = await request.json()
    user = db.query(models.User).filter(models.User.id == user_id).first()
    user.notification_time = data.get("time")
    db.commit()
    return {"status": "success"}

@app.get("/api/notification-time")
def get_notification_time(request: Request, db: Session = Depends(get_db)):
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return {"time": user.notification_time or "09:00"}



scheduler = BackgroundScheduler()
scheduler.add_job(check_expiry_and_queue_notifications, 'interval', minutes=1)
scheduler.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)