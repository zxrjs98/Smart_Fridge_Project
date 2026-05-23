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

# 환경 변수 로드
load_dotenv()

app = FastAPI()

# DB 테이블 자동 생성
models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    response.set_cookie(key="user_id", value=str(user.id), httponly=True)
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
    user_id = request.cookies.get("user_id")
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
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
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    return templates.TemplateResponse(request=request, name="profile.html", context={"user": user})

@app.post("/update-profile")
def update_profile(current_pw: str = Form(None), new_pw: str = Form(None), new_pw_confirm: str = Form(None), db: Session = Depends(get_db), request: Request = None):
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

# ---------------------------------------------------------
# 2. 메인 서비스 (냉장고 관리)
# ---------------------------------------------------------
@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        return RedirectResponse(url="/", status_code=303)
    
    user_id = int(user_id_str)
    try:
        items = db.query(models.Item).filter(models.Item.user_id == user_id).order_by(models.Item.expiry_date.is_(None), models.Item.expiry_date.asc()).all()
        today = date.today()
        processed_items = []
        for item in items:
            d_day = (item.expiry_date - today).days if item.expiry_date else None
            processed_items.append({"id": item.id, "name": item.name, "expiry_date": item.expiry_date, "d_day": d_day})
        
        response = templates.TemplateResponse(request=request, name="index.html", context={"items": processed_items, "current_user": user_id})
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
    user_id = int(request.cookies.get("user_id"))
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
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    user_id = int(user_id_str)

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
    user_id = int(request.cookies.get("user_id"))
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
    user_id = request.cookies.get("user_id") 
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    shopping_list = db.query(models.ShoppingList).filter(models.ShoppingList.user_id == int(user_id)).all()
    return templates.TemplateResponse(request=request, name="shopping.html", context={"items": shopping_list})

@app.post("/shopping/add")
def add_shopping_item(request: Request, item_name: str = Form(...), db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return {"error": "로그인이 필요합니다."}
    existing_item = db.query(models.ShoppingList).filter(models.ShoppingList.user_id == int(user_id), models.ShoppingList.item_name == item_name).first()
    if existing_item:
        return RedirectResponse(url="/shopping", status_code=303)
    new_item = models.ShoppingList(item_name=item_name, user_id=int(user_id), is_bought=False)
    db.add(new_item)
    db.commit()
    return RedirectResponse(url="/shopping", status_code=303)

@app.post("/shopping/delete/{item_id}")
def delete_shopping_item(request: Request, item_id: int = Path(...), db: Session = Depends(get_db)):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    item_to_delete = db.query(models.ShoppingList).filter(models.ShoppingList.id == item_id, models.ShoppingList.user_id == int(user_id)).first()
    if not item_to_delete:
        return {"error": "삭제 권한이 없거나 존재하지 않는 항목입니다."}
    db.delete(item_to_delete)
    db.commit()
    return RedirectResponse(url="/shopping", status_code=303)

# ---------------------------------------------------------
# 4. 레시피 및 OCR 스캔 연동
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

# 네이버 OCR 통신 코드

import json
from openai import OpenAI

@app.post("/scan_receipt")
async def scan_receipt(
    request: Request, 
    receipt: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        return {"status": "error", "message": "로그인이 필요합니다."}
    user_id = int(user_id_str)

    invoke_url = os.getenv("OCR_INVOKE_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY") # 🔥 OpenAI API 키 로드

    if not invoke_url or not secret_key:
        return {"status": "error", "message": "네이버 OCR API 키가 없습니다. .env 파일을 확인해주세요!"}
    if not openai_api_key:
        return {"status": "error", "message": "OpenAI API 키가 없습니다. .env 파일에 OPENAI_API_KEY를 추가해주세요!"}

    try:
        # -------------------------------------------------------------
        # 1단계: 네이버 OCR로 영수증 스캔 (기존과 동일)
        # -------------------------------------------------------------
        image_bytes = await receipt.read()
        ext = receipt.filename.split('.')[-1] if '.' in receipt.filename else 'png'

        request_json = {
            'images': [{'format': ext, 'name': 'receipt_test'}],
            'requestId': str(uuid.uuid4()),
            'version': 'V2',
            'timestamp': int(round(time.time() * 1000)),
            'receipt': {
                'enable': True 
            }
        }

        payload = {'message': json.dumps(request_json).encode('UTF-8')}
        files = [('file', (receipt.filename, image_bytes, receipt.content_type))]
        headers = {'X-OCR-SECRET': secret_key}

        response = requests.post(invoke_url, headers=headers, data=payload, files=files)
        result = response.json()

        # 영수증에서 뽑아낸 '날것의' 텍스트 리스트 만들기
        raw_items = []
        if 'images' in result and len(result['images']) > 0:
            image_data = result['images'][0]
            if 'receipt' in image_data and 'result' in image_data['receipt']:
                receipt_result = image_data['receipt']['result']
                if 'subResults' in receipt_result and len(receipt_result['subResults']) > 0:
                    items = receipt_result['subResults'][0].get('items', [])
                    for item in items:
                        name = item.get('name', {}).get('text', '').strip()
                        if name:
                            raw_items.append(name)

        if not raw_items:
            # 영수증에서 아무것도 못 읽었을 때의 방어 로직
            return {"status": "success", "items": [{"name": "인식 불가", "expiry_date": ""}], "saved_count": 0}

        # -------------------------------------------------------------
        # 🧠 2단계: OpenAI (gpt-4o-mini) LLM으로 초지능 데이터 세탁!
        # -------------------------------------------------------------
        client = OpenAI(api_key=openai_api_key)

        # AI를 조종하는 프롬프트 (여기에 규칙을 마음껏 추가할 수 있습니다!)
        system_prompt = """
        너는 스마트 냉장고의 식재료 분류 AI 데이터 엔지니어 역할을 맡고 있어.
        사용자가 영수증의 상품명 리스트를 주면, 요리에 쓰이는 '표준 식재료명'으로만 정제해서 JSON 형태로 반환해.
        
        [정제 규칙]
        1. 브랜드명(예: 롯데), 용도(예: 구이용, 찌개용), 용량, 괄호 안의 내용은 완벽히 제거해.
        2. 오타(예: 검은콩무유 -> 우유)나 고유 제품명(예: 제빵왕김탁구 -> 빵)은 문맥을 파악해서 '표준 재료명'으로 바꿔.
        3. 공산품(예: 종량제봉투, 숟가락)이나 먹을 수 없는 식재료가 아닌 것들은 아예 결과 리스트에서 제외해버려.
        4. 응답은 반드시 {"items": ["돼지고기", "우유", "칼국수면"]} 같은 형태의 JSON 포맷으로 대답해야 해.
        """

        # GPT에게 날것의 데이터를 던지고 결과 받기 (가장 빠르고 저렴한 gpt-4o-mini 모델 사용)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음 영수증 리스트를 정제해줘: {json.dumps(raw_items, ensure_ascii=False)}"}
            ],
            response_format={"type": "json_object"}
        )

        # AI가 예쁘게 포장해서 준 JSON 까보기
        ai_response = json.loads(completion.choices[0].message.content)
        clean_item_names = ai_response.get("items", [])

        # -------------------------------------------------------------
        # 3단계: 정제된 이름으로 DB에 저장하기
        # -------------------------------------------------------------
        saved_count = 0
        final_parsed_items = []

        for clean_name in clean_item_names:
            final_name = clean_name[:30] # DB 터짐 방지 30자 커트
            expiry_str = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')
            expiry = datetime.strptime(expiry_str, '%Y-%m-%d').date()

            new_item = models.Item(name=final_name, expiry_date=expiry, user_id=user_id)
            db.add(new_item)
            saved_count += 1
            
            final_parsed_items.append({"name": final_name, "expiry_date": expiry_str})
        
        db.commit() # DB 쾅! 저장 완료

        return {"status": "success", "items": final_parsed_items, "saved_count": saved_count}

    except Exception as e:
        import traceback
        traceback.print_exc() 
        return {"status": "error", "message": f"서버 에러 발생: {str(e)}"}
    
# ---------------------------------------------------------
# 5. 웹 푸시 알림 및 스케줄러 시스템
# ---------------------------------------------------------
@app.get("/sw.js")
def get_service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript")

@app.get("/api/notifications/check")
def check_notifications(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        raise HTTPException(status_code=401)
    
    user_id = int(user_id_str)
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
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    
    subscription_info = await request.json()
    existing = db.query(models.PushSubscription).filter(models.PushSubscription.user_id == int(user_id)).first()
    if existing:
        existing.subscription_info = json.dumps(subscription_info)
    else:
        new_sub = models.PushSubscription(user_id=int(user_id), subscription_info=json.dumps(subscription_info))
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
            items = db.query(models.Item).filter(models.Item.user_id == user.id, models.Item.expiry_date.isnot(None)).all()
            urgent_items = []
            for item in items:
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
    user_id = request.cookies.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401)
    data = await request.json()
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    user.notification_time = data.get("time")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)