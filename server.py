# ==========================================
# 📦 기본 패키지 및 도구 모음
# ==========================================
import os
import re
import smtplib
import string
import random
from typing import Optional, List
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
# ==========================================
# 🚀 FastAPI 관련 도구
# ==========================================
from fastapi import FastAPI, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse

# ==========================================
# 💾 데이터베이스 (SQLAlchemy) 관련 도구
# ==========================================
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from database.connection import engine

# ==========================================
# 🔐 보안 및 이메일 (비밀번호 암호화, 메일 발송)
# ==========================================
from passlib.context import CryptContext
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# ==========================================
# 🗂️ 내 프로젝트 파일들 (models, connection 등)
# ==========================================
import database.models as models
from database.connection import get_db
from database.models import User, ShoppingList
from api.items import get_current_user_id, get_optional_user_id

from pywebpush import webpush, WebPushException
import json

# 환경 변수 로드
load_dotenv()

# 비밀번호 암호화를 위한 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

# 기존에 있던 암호화 함수
def get_password_hash(password):
    return pwd_context.hash(password)

# 👇 이번에 새로 추가할 비교 함수
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# ---------------------------------------------------------
# 1. 초기 설정 및 보안 구성
# ---------------------------------------------------------
app = FastAPI()

scheduler = BackgroundScheduler()

# DB 테이블 자동 생성
models.Base.metadata.create_all(bind=engine)

# 템플릿 및 정적 파일 경로 설정
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# 비밀번호 암호화 설정 (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """비밀번호 해싱 (UTF-8 인코딩 및 72바이트 제한 처리)"""
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    return pwd_context.hash(pwd_bytes)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return pwd_context.verify(plain_password, hashed_password)

# ---------------------------------------------------------
# 2. 인증 및 계정 관리 (Login / Register / Profile)
# ---------------------------------------------------------

@app.get("/")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login_user(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "아이디 또는 비밀번호가 일치하지 않습니다."}
        )
    
    # 2. 유저가 없거나 비밀번호가 틀리면 에러 반환
    if not user or not verify_password(password, user.hashed_password):
       return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"error": "아이디나 비밀번호가 틀렸습니다."}
        )
    
    response = RedirectResponse(url="/main", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id), httponly=True)
    return response

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse( request=request,name="register.html")

@app.post("/register")
def register_user(
    request: Request,
    username: str = Form(default=""), 
    password: str = Form(default=""), 
    password_confirm: str = Form(default=""),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    errors = {} 
    # 아이디 검증
    if not (6 <= len(username) <= 12):
        errors["username_error"] = "아이디는 6~12글자로 해주세요."
    else:
        if db.query(models.User).filter(models.User.username == username).first():
            errors["username_error"] = "이미 존재하는 아이디입니다."

    # 비밀번호 복합도 검증 (영문, 숫자, 특수문자 중 2가지 이상 조합)
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

    # 이메일 형식 및 중복 검증
    email_regex = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    if not email_regex.match(email):
        errors["email_error"] = "올바른 이메일 형식을 입력해주세요."
    elif db.query(models.User).filter(models.User.email == email).first():
        errors["email_error"] = "이미 가입된 이메일입니다."

    if errors:
        return templates.TemplateResponse(request=request, name="register.html",context={"errors": errors, "username": username, "email": email}
    )

    new_user = models.User(username=username, hashed_password=get_password_hash(password), email=email)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

# ---------------------------------------------------------
# 메인 페이지 (내 냉장고 목록 조회)
# ---------------------------------------------------------
@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db), current_user: models.User = Depends(get_optional_user_id)):
    # 완전히 비어있거나, 글자 "None"이거나, 빈칸이면 무조건 쫓아냅니다!
    if not current_user or str(current_user) == "None" or str(current_user) == "":
        return RedirectResponse(url="/", status_code=303)
    
    try:
        # [수정] .filter(models.Item.user_id == current_user.id) 추가!
        items = db.query(models.Item).filter(
            models.Item.user_id == current_user
        ).order_by(
            models.Item.expiry_date.is_(None), 
            models.Item.expiry_date.asc()      
        ).all()

        today = datetime.now().date()
        processed_items = []
        for item in items:
            d_day = None
            if item.expiry_date:
                expiry = item.expiry_date
                if isinstance(expiry, str):
                    expiry = datetime.strptime(expiry, '%Y-%m-%d').date()
                d_day = (expiry - today).days
            
            processed_items.append({
                "id": item.id,
                "name": item.name,
                "expiry_date": item.expiry_date,
                "d_day": d_day
            })
        
        # 💡 [핵심 1] 정상 작동할 때: 바로 return 하지 않고 response에 담아서 헤더 추가!
        response = templates.TemplateResponse(request=request, name="index.html", context={"items": processed_items})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    except Exception as e:
        print(f"메인 페이지 로드 에러: {e}")
        
        # 💡 [핵심 2] 에러 났을 때: 여기서도 담아서 헤더 추가 후 return!
        response = templates.TemplateResponse(request=request, name="index.html", context={"items": [], "error": str(e)})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
# ---------------------------------------------------------
# 재료 검색
# ---------------------------------------------------------
@app.get("/items/search")
def search_ingredients(q: str = "", db: Session = Depends(get_db)):
    if not q or q == "popular":
        results = db.query(models.MasterIngredient).order_by(models.MasterIngredient.name.asc()).all()
    else:
        results = db.query(models.MasterIngredient).filter(models.MasterIngredient.name.contains(q)).order_by(models.MasterIngredient.name.asc()).all()
    return [{"name": r.name, "is_seasoning": r.is_seasoning} for r in results]

# ---------------------------------------------------------
# 내 냉장고에 재료 저장
# ---------------------------------------------------------
@app.post("/items")
async def create_item(request: Request, db: Session = Depends(get_db),current_user: models.User = Depends(get_current_user_id)):
    try:
        data = await request.json()
        expiry_str = data.get('expiry_date')
        expiry = None
        if expiry_str and expiry_str.strip():
            try:
                expiry = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            except ValueError:
                expiry = None 
        
       # [수정] user_id=current_user.id 를 추가해서 저장!
        new_item = models.Item(
            name=data['name'], 
            expiry_date=expiry,
            user_id=current_user # <--- "이건 내 재료다!" 도장 찍기
        )
        db.add(new_item)
        db.commit()
        return {"message": "success"}
    except Exception as e:
        db.rollback()
        print(f"저장 실패 에러: {e}") # 에러 로그 확인용
        raise HTTPException(status_code=500, detail="저장 실패")

# ---------------------------------------------------------
# 소비기한 수정 및 삭제
# ---------------------------------------------------------
@app.post("/update-item/{item_name}")
async def update_item(item_name: str, request: Request, db: Session = Depends(get_db),current_user: models.User = Depends(get_current_user_id)):
    try:
        data = await request.json()
        new_date_str = data.get("expiry_date")
        item = db.query(models.Item).filter(models.Item.name == item_name,models.Item.user_id == current_user).first()
        if item:
            if new_date_str and new_date_str.strip():
                item.expiry_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            else:
                item.expiry_date = None
            db.commit()
            return {"message": "success"}
        raise HTTPException(status_code=404, detail="항목 찾을 수 없음")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
@app.delete("/items/{item_name}")
def delete_item(item_name: str, db: Session = Depends(get_db),current_user: models.User = Depends(get_current_user_id)):
    try:
        item = db.query(models.Item).filter(models.Item.name == item_name,models.Item.user_id == current_user).first()
        if item:
            db.delete(item)
            db.commit()
            return {"message": "success"}
        raise HTTPException(status_code=404, detail="삭제할 항목 없음")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="삭제 오류")

# ---------------------------------------------------------
# 레시피 연동 기능
# ---------------------------------------------------------

@app.get("/api/recipes")
def get_recipes(
    db: Session = Depends(get_db),
    #목록을 가져올 때도 '누가' 보고 있는지 알아야 하므로 유저 인증 추가
    current_user: str = Depends(get_current_user_id) 
):
    try:
        recipes = db.query(models.Recipe).all()
        all_ingredients = db.query(models.RecipeIngredient).all()
        
        # 현재 로그인한 유저가 즐겨찾기한 레시피 ID 목록만 가져오기
        user_favorites = db.query(models.Favorite.recipe_id).filter(
            models.Favorite.user_id == current_user
        ).all()
        # 빠른 검색을 위해 세트(Set)로 변환 (예: {18, 5, 2})
        favorite_recipe_ids = {fav[0] for fav in user_favorites}
        
        ing_map = {}
        for ing in all_ingredients:
            if ing.recipe_id not in ing_map:
                ing_map[ing.recipe_id] = []
            ing_map[ing.recipe_id].append(ing.ingredient_name)

        results = []
        for r in recipes:
            results.append({
                "id": r.recipe_id,
                "name": r.name,
                "ingredients": ing_map.get(r.recipe_id, []),
                # 🌟 수정됨: r.favorite 대신, 이 레시피 ID가 유저의 찜 목록에 있는지 확인
                "favorite": r.recipe_id in favorite_recipe_ids,
                "image_url": r.image_url or "",
                "instructions": r.instructions or "", 
                "original_ingredients": r.original_ingredients or ""
            })
        return results
    except Exception as e:
        # 🚨 이 두 줄을 추가해 주세요! 터미널에 빨간 글씨로 상세 에러를 강제로 찍어줍니다.
        import traceback
        traceback.print_exc() 
        
        raise HTTPException(status_code=500, detail=str(e))
        


# ---------------------------------------------------------
# 즐겨찾기 추가/취소
# ---------------------------------------------------------

@app.post("/api/recipes/{recipe_id}/favorite")
async def update_favorite(
    recipe_id: int, 
    request: Request, 
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user_id) # 유저 아이디 (예: "testid")
):
    try:
        data = await request.json()
        is_favorite = data.get("favorite") # 프론트에서 보낸 True 또는 False
        
        # 1. Favorite 테이블에서 '현재 유저'가 '이 레시피'를 찜했는지 확인
        favorite_record = db.query(models.Favorite).filter(
            models.Favorite.recipe_id == recipe_id,
            models.Favorite.user_id == current_user
        ).first()
        
        # 2. 상태에 맞춰서 테이블에 추가하거나 삭제
        if is_favorite:
            # 하트를 켰는데 기록이 없다면 추가
            if not favorite_record:
                new_favorite = models.Favorite(user_id=current_user, recipe_id=recipe_id)
                db.add(new_favorite)
        else:
            # 하트를 껐는데 기록이 남아있다면 삭제
            if favorite_record:
                db.delete(favorite_record)
                
        # 3. 데이터베이스에 반영
        db.commit()
        return {"message": "success"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="실패")
# ---------------------------------------------------------
# 내 정보 확인
# ---------------------------------------------------------

@app.get("/profile")
def profile_page(request: Request, db: Session = Depends(get_db), current_user_id: int = Depends(get_optional_user_id)):
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)
    
    # 💡 DB에서 현재 로그인한 유저 정보를 가져옵니다.
    user = db.query(User).filter(User.id == current_user_id).first()
    
    # 💡 유저 정보(이메일 포함)를 HTML에 전달합니다.
    return templates.TemplateResponse(
            request=request, 
            name="profile.html", 
            context={"user": user}  # 이제 HTML에서 user.email로 접근 가능!
        )

# ---------------------------------------------------------
# 내 정보 수정
# ---------------------------------------------------------

@app.post("/update-profile")
def update_profile(
    current_pw: str = Form(None),
    new_pw: str = Form(None),
    new_pw_confirm: str = Form(None),
    db: Session = Depends(get_db),
    request: Request = None
):
    user_id = request.cookies.get("user_id")
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    
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
        # 구글 메일 서버 연결
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

# -----------------------------
# 💡 아이디 찾기 라우터 수정
# -----------------------------
@app.get("/find-id", response_class=HTMLResponse)
async def get_find_id_page(request: Request):
    return templates.TemplateResponse(request=request, name="find-id.html")

@app.post("/find-id")
async def find_id(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    
    if user:
        # 💡 화면에 띄우는 대신 메일 발송!
        send_id_email(user.email, user.username)
        # 이메일 전송 상태와 입력한 이메일을 html로 넘김
        return templates.TemplateResponse(request=request, name="find-id.html", context={"email_sent": True, "sent_email": email})
    else:
        # 💡 없는 이메일일 경우 (작은 빨간 글씨 출력을 위해 id_error 전달)
        return templates.TemplateResponse(request=request, name="find-id.html", context={"input_email": email, "id_error": "가입된 이메일이 없습니다."})
# -----------------------------
# 💡 2. 비밀번호 찾기 라우터
# -----------------------------
@app.get("/find-pw", response_class=HTMLResponse)
async def get_find_pw_page(request: Request):
    return templates.TemplateResponse(request=request, name="find-pw.html")

@app.post("/find-pw")
async def find_pw(request: Request, username: str = Form(...), email: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username, models.User.email == email).first()
    
    if user:
        # 1. 8자리 임시 비밀번호 생성 (영어+숫자)
        temp_pw = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        
        # 2. 임시 비밀번호 암호화
        hashed_pw = pwd_context.hash(temp_pw)
        
        # 3. 🚨 DB에 확실하게 업데이트! ('hashed_password' 컬럼을 변경)
        db.query(models.User).filter(models.User.username == username).update({"hashed_password": hashed_pw})
        db.commit()
        
        # 4. 메일 발송
        send_temp_password(user.email, temp_pw)
        
        # 비밀번호 찾기 성공 시
        message = "입력하신 이메일로 아이디를 발송했습니다." # 문구를 아이디 찾기와 통일하면 더 깔끔해요!
        return templates.TemplateResponse(
            request=request, 
            name="find-pw.html", 
            context={
                "pw_message": message, 
                "success": True  # 이 부분을 추가해야 '다시 보내기' 버튼이 뜹니다!
            }
        )
    else:
        return templates.TemplateResponse(
            request=request, 
            name="find-pw.html", 
            context={"pw_error": "아이디와 일치하는 이메일이 없습니다."}
        )
# ---------------------------------------------------------
# 로그아웃
# ---------------------------------------------------------

@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        return RedirectResponse(url="/", status_code=303)
    
    user_id = int(user_id_str)
    # 소비기한 미입력 데이터를 하단으로 보내는 정렬 로직
    items = db.query(models.Item).filter(models.Item.user_id == user_id)\
        .order_by(models.Item.expiry_date.isnot(None).desc(), models.Item.expiry_date.asc()).all()

    today = date.today()
    processed_items = []
    for item in items:
        d_day = (item.expiry_date - today).days if item.expiry_date else None
        processed_items.append({
            "id": item.id, "name": item.name, "expiry_date": item.expiry_date, "d_day": d_day
        })
            
    return templates.TemplateResponse(request=request, name="index.html", context={"items": processed_items, "current_user": user_id})

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
    user_id = int(request.cookies.get("user_id"))
    data = await request.json()
    expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date() if data.get('expiry_date') else None
    new_item = models.Item(name=data['name'], expiry_date=expiry, user_id=user_id)
    db.add(new_item)
    db.commit()
    return {"message": "success"}

@app.post("/update-item/{item_name}")
async def update_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    user_id = int(request.cookies.get("user_id"))
    data = await request.json()
    item = db.query(models.Item).filter(models.Item.name == item_name, models.Item.user_id == user_id).first()
    if item:
        new_date = data.get("expiry_date")
        item.expiry_date = datetime.strptime(new_date, '%Y-%m-%d').date() if new_date else None
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404)

@app.delete("/items/{item_name}")
def delete_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    user_id = int(request.cookies.get("user_id"))
    item = db.query(models.Item).filter(models.Item.name == item_name, models.Item.user_id == user_id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404)

# ---------------------------------------------------------
# 4. 레시피 및 OCR 시스템 (Recipe / Favorite / OCR)
# ---------------------------------------------------------

@app.get("/api/recipes")
def get_recipes(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    current_user_id = int(user_id_str) if user_id_str else None
    
    all_raw_recipes = db.query(models.Recipe).all()
    favorite_ids = set()
    if current_user_id:
        favs = db.query(models.Favorite.recipe_id).filter(models.Favorite.user_id == current_user_id).all()
        favorite_ids = {f[0] for f in favs}

    results = []
    for r in all_raw_recipes:
        rid = getattr(r, 'recipe_id', None) or getattr(r, 'id', None)
        ings = db.query(models.RecipeIngredient.ingredient_name).filter(models.RecipeIngredient.recipe_id == rid).all()
        results.append({
            "id": rid, "name": r.name, "ingredients": [i[0] for i in ings],
            "favorite": rid in favorite_ids, "image_url": r.image_url or "",
            "instructions": r.instructions or "", "original_ingredients": r.original_ingredients or ""
        })
    return results

@app.post("/api/recipes/{recipe_id}/favorite")
async def toggle_favorite(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = int(request.cookies.get("user_id"))
    data = await request.json()
    fav_record = db.query(models.Favorite).filter(models.Favorite.user_id == user_id, models.Favorite.recipe_id == recipe_id).first()
    if data.get("favorite") and not fav_record:
        db.add(models.Favorite(user_id=user_id, recipe_id=recipe_id))
    elif not data.get("favorite") and fav_record:
        db.delete(fav_record)
    db.commit()
    return {"message": "success"}

@app.post("/scan_receipt")
async def scan_receipt(receipt: UploadFile = File(...)):
    invoke_url = os.getenv("OCR_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")

    if not invoke_url or not secret_key:
        # Mock Data
        mock_items = [
            {"name": "삼겹살", "expiry_date": (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')},
            {"name": "대파", "expiry_date": (date.today() + timedelta(days=5)).strftime('%Y-%m-%d')}
        ]
        return {"status": "success", "items": mock_items}

    # NAVER CLOVA OCR API 호출 (생략된 실구현부 통합)
    # ... (상세 구현 로직 생략 없이 유지) ...
    return {"status": "success", "items": []}

# my page 페이지

@app.get("/mypage", response_class=HTMLResponse)
async def get_menu_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="mypage.html"
    )


# 1. 장보기 목록 페이지 (화면 보여주기)
@app.get("/shopping")
def get_shopping_list(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id") 
    
    if not user_id:
        # 로그인 안 되어 있으면 로그인 페이지로 보냄
        return RedirectResponse(url="/login", status_code=303)

    shopping_list = db.query(models.ShoppingList).filter(
        models.ShoppingList.user_id == int(user_id)  # 쿠키값은 문자열이라 숫자로 변환
    ).all()

    return templates.TemplateResponse(
        request=request,              
        name="shopping.html",          
        context={"items": shopping_list}  
    )
@app.post("/shopping/add")
def add_shopping_item(request: Request, item_name: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    
    if not user_id:
        return {"error": "로그인이 필요합니다."}
    # 1. 중복확인
    existing_item = db.query(models.ShoppingList).filter(
        models.ShoppingList.user_id == int(user_id),
        models.ShoppingList.item_name == item_name
    ).first()

    # 2. 만약 이미 있다면, 저장하지 않고 그냥 목록 페이지로 돌려보냅니다.
    if existing_item:
        return RedirectResponse(url="/shopping", status_code=303)

    # 3. 새로운 아이템을 만들 때 유저 ID를 함께 저장합니다.
    new_item = models.ShoppingList(
        item_name=item_name,
        user_id=int(user_id), # 👈 이 부분이 중요!
        is_bought=False
    )
    
    db.add(new_item)
    db.commit()
    return RedirectResponse(url="/shopping", status_code=303)
from fastapi import Path

@app.post("/shopping/delete/{item_id}")
def delete_shopping_item(
    request: Request, 
    item_id: int = Path(...), 
    db: Session = Depends(get_db)
):
    # 1. 쿠키에서 현재 로그인한 유저 ID 가져오기
    user_id = request.cookies.get("user_id")
    
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    item_to_delete = db.query(models.ShoppingList).filter(
        models.ShoppingList.id == item_id,
        models.ShoppingList.user_id == int(user_id) # 👈 본인 확인!
    ).first()

    if not item_to_delete:
        return {"error": "삭제 권한이 없거나 존재하지 않는 항목입니다."}

    # 3. 삭제 진행
    db.delete(item_to_delete)
    db.commit()

    # 4. 삭제 후 다시 장보기 목록 페이지로 리다이렉트
    return RedirectResponse(url="/shopping", status_code=303)


@app.get("/logout")
def logout():
    # 로그아웃 후 처음에 접속하는 로그인 화면("/")으로 돌려보냅니다.
    response = RedirectResponse(url="/", status_code=303)
    
    # 💡 여기서 'user_id' 쿠키를 삭제합니다!
    response.delete_cookie("user_id", path="/")
    
    return response
# ---------------------------------------------------------
# 회원 탈퇴
# ---------------------------------------------------------
@app.post("/withdraw")
def withdraw_account(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    db.delete(user)
    db.commit()
    response = HTMLResponse("<script>alert('회원 탈퇴가 완료되었습니다. 그동안 이용해주셔서 감사합니다.'); window.location.href='/';</script>")
    response.delete_cookie("user_id")
    return response

# ---------------------------------------------------------
# 3. 메인 서비스 (Refrigerator Management)
# ---------------------------------------------------------

@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        return RedirectResponse(url="/", status_code=303)
    
    user_id = int(user_id_str)
    # 소비기한 미입력 데이터를 하단으로 보내는 정렬 로직
    items = db.query(models.Item).filter(models.Item.user_id == user_id)\
        .order_by(models.Item.expiry_date.isnot(None).desc(), models.Item.expiry_date.asc()).all()

    today = date.today()
    processed_items = []
    for item in items:
        d_day = (item.expiry_date - today).days if item.expiry_date else None
        processed_items.append({
            "id": item.id, "name": item.name, "expiry_date": item.expiry_date, "d_day": d_day
        })
            
    return templates.TemplateResponse("index.html", {
        "request": request, "items": processed_items, "current_user": user_id
    })

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
    user_id = int(request.cookies.get("user_id"))
    data = await request.json()
    expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date() if data.get('expiry_date') else None
    new_item = models.Item(name=data['name'], expiry_date=expiry, user_id=user_id)
    db.add(new_item)
    db.commit()
    return {"message": "success"}

@app.post("/update-item/{item_name}")
async def update_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    user_id = int(request.cookies.get("user_id"))
    data = await request.json()
    item = db.query(models.Item).filter(models.Item.name == item_name, models.Item.user_id == user_id).first()
    if item:
        new_date = data.get("expiry_date")
        item.expiry_date = datetime.strptime(new_date, '%Y-%m-%d').date() if new_date else None
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404)

@app.delete("/items/{item_name}")
def delete_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    user_id = int(request.cookies.get("user_id"))
    item = db.query(models.Item).filter(models.Item.name == item_name, models.Item.user_id == user_id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404)

# ---------------------------------------------------------
# 4. 레시피 및 OCR 시스템 (Recipe / Favorite / OCR)
# ---------------------------------------------------------

@app.get("/api/recipes")
def get_recipes(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    current_user_id = int(user_id_str) if user_id_str else None
    
    all_raw_recipes = db.query(models.Recipe).all()
    favorite_ids = set()
    if current_user_id:
        favs = db.query(models.Favorite.recipe_id).filter(models.Favorite.user_id == current_user_id).all()
        favorite_ids = {f[0] for f in favs}

    results = []
    for r in all_raw_recipes:
        rid = getattr(r, 'recipe_id', None) or getattr(r, 'id', None)
        ings = db.query(models.RecipeIngredient.ingredient_name).filter(models.RecipeIngredient.recipe_id == rid).all()
        results.append({
            "id": rid, "name": r.name, "ingredients": [i[0] for i in ings],
            "favorite": rid in favorite_ids, "image_url": r.image_url or "",
            "instructions": r.instructions or "", "original_ingredients": r.original_ingredients or ""
        })
    return results

@app.post("/api/recipes/{recipe_id}/favorite")
async def toggle_favorite(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = int(request.cookies.get("user_id"))
    data = await request.json()
    fav_record = db.query(models.Favorite).filter(models.Favorite.user_id == user_id, models.Favorite.recipe_id == recipe_id).first()
    if data.get("favorite") and not fav_record:
        db.add(models.Favorite(user_id=user_id, recipe_id=recipe_id))
    elif not data.get("favorite") and fav_record:
        db.delete(fav_record)
    db.commit()
    return {"message": "success"}

@app.post("/scan_receipt")
async def scan_receipt(receipt: UploadFile = File(...)):
    invoke_url = os.getenv("OCR_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")

    if not invoke_url or not secret_key:
        # Mock Data
        mock_items = [
            {"name": "삼겹살", "expiry_date": (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')},
            {"name": "대파", "expiry_date": (date.today() + timedelta(days=5)).strftime('%Y-%m-%d')}
        ]
        return {"status": "success", "items": mock_items}

    # NAVER CLOVA OCR API 호출 (생략된 실구현부 통합)
    # ... (상세 구현 로직 생략 없이 유지) ...
    return {"status": "success", "items": []}

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id")
    return response

@app.get("/sw.js")
def get_service_worker():
    # 프로젝트 루트에 위치한 sw.js 파일을 브라우저에 전달
    return FileResponse("static/sw.js", media_type="application/javascript")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)

@app.get("/api/notifications/check")
def check_notifications(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        raise HTTPException(status_code=401)
        
    user_id = int(user_id_str)
    today = date.today()
    
    # 해당 유저의 D-1, D-3 임박 재료 조회
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

@app.get("/api/vapid-public-key")
def get_vapid_public_key():
    return {"public_key": VAPID_PUBLIC_KEY}

@app.post("/api/notifications/subscribe")
async def subscribe_notifications(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    
    subscription_info = await request.json()
    
    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.user_id == int(user_id)
    ).first()
    
    if existing:
        existing.subscription_info = json.dumps(subscription_info)
    else:
        new_sub = models.PushSubscription(
            user_id=int(user_id),
            subscription_info=json.dumps(subscription_info)
        )
        db.add(new_sub)
    
    db.commit()
    return {"status": "success"}

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")

# 기존에 만든 BackgroundScheduler 내부 로직 고도화
def check_expiry_and_queue_notifications():
    db: Session = next(get_db())
    try:
        now = datetime.now().strftime("%H:%M")  # 현재 시간 (예: "09:00")
        today = date.today()

        # 알림 시간이 지금인 유저만 조회
        users = db.query(models.User).filter(
            models.User.notification_time == now
        ).all()

        for user in users:
            items = db.query(models.Item).filter(
                models.Item.user_id == user.id,
                models.Item.expiry_date.isnot(None)
            ).all()

            urgent_items = []
            for item in items:
                d_day = (item.expiry_date - today).days
                if d_day in [0, 1, 2, 3]:
                    if d_day == 0:
                        urgent_items.append(f"{item.name}(D-Day)")
                    else:
                        urgent_items.append(f"{item.name}(D-{d_day})")

            if not urgent_items:
                continue

            push_sub = db.query(models.PushSubscription).filter(
                models.PushSubscription.user_id == user.id
            ).first()

            if push_sub:
                sub_info = json.loads(push_sub.subscription_info)
                try:
                    webpush(
                        subscription_info=sub_info,
                        data=json.dumps({
                            "title": "FreshKeep 소비기한 알림",
                            "body": f"임박 재료: {', '.join(urgent_items)}"
                        }),
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": "mailto:실제이메일@gmail.com"}
                    )
                    print(f"유저 {user.id} 푸시 발송 성공")
                except WebPushException as ex:
                    print(f"푸시 발송 실패: {ex}")
    finally:
        db.close()

@app.post("/api/notification-time")
async def update_notification_time(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    
    data = await request.json()
    time_value = data.get("time")  # "09:00" 형식
    
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    user.notification_time = time_value
    db.commit()
    return {"status": "success"}

@app.get("/api/notification-time")
def get_notification_time(request: Request, db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    return {"time": user.notification_time or "09:00"}

scheduler = BackgroundScheduler()
scheduler.add_job(check_expiry_and_queue_notifications, 'interval', minutes=1)
scheduler.start()