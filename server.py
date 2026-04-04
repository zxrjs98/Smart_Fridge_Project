import os
import time
import requests
import uuid
import base64
import re
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from passlib.context import CryptContext

import database.models as models
from database.connection import get_db, engine
from api.items import get_current_user_id, get_optional_user_id
from database.models import User

# ---------------------------------------------------------
# 비밀번호 암호화 및 앱 초기화 설정
# ---------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

app = FastAPI()

# 💡 DB 테이블 자동 생성 (서버 켜질 때 없으면 알아서 만듦)
models.Base.metadata.create_all(bind=engine)

# HTML 및 정적 파일 경로 설정
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# 로그인 및 회원가입
# ---------------------------------------------------------
@app.get("/")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.username == username).first()
    
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            name="login.html", 
            context={"request": request, "error": "아이디나 비밀번호가 틀렸습니다."}
        )
    
    response = RedirectResponse(url="/main", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

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

    if not (6 <= len(username) <= 12):
        errors["username_error"] = "아이디는 6~12글자로 해주세요."
    else:
        existing_user = db.query(models.User).filter(models.User.username == username).first()
        if existing_user:
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
        errors["confirm_error"] = "비밀번호가 다릅니다!!"

    email_regex = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    if not email_regex.match(email):
        errors["email_error"] = "올바른 이메일 형식을 입력해주세요."
    else:
        existing_email = db.query(models.User).filter(models.User.email == email).first()
        if existing_email:
            errors["email_error"] = "이미 가입된 이메일입니다."

    if errors:
        return templates.TemplateResponse(
            name="register.html", 
            context={
                "request": request, 
                "errors": errors, 
                "username": username,
                "email": email 
            }
        )
    
    hashed_pw = get_password_hash(password)
    new_user = models.User(username=username, hashed_password=hashed_pw,email=email)
    db.add(new_user)
    db.commit()

    return RedirectResponse(url="/", status_code=303)

# ---------------------------------------------------------
# 메인 페이지 (내 냉장고 목록)
# ---------------------------------------------------------
@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db), current_user: models.User = Depends(get_optional_user_id)):
    if not current_user or str(current_user) == "None" or str(current_user) == "":
        return RedirectResponse(url="/", status_code=303)
    
    try:
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
        
        response = templates.TemplateResponse("index.html", {"request": request, "items": processed_items})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    except Exception as e:
        print(f"메인 페이지 로드 에러: {e}")
        response = templates.TemplateResponse("index.html", {"request": request, "items": [], "error": str(e)})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

# ---------------------------------------------------------
# 재료 추가, 수정, 삭제
# ---------------------------------------------------------
@app.get("/items/search")
def search_ingredients(q: str = "", db: Session = Depends(get_db)):
    if not q or q == "popular":
        results = db.query(models.MasterIngredient).order_by(models.MasterIngredient.name.asc()).all()
    else:
        results = db.query(models.MasterIngredient).filter(models.MasterIngredient.name.contains(q)).order_by(models.MasterIngredient.name.asc()).all()
    return [{"name": r.name, "is_seasoning": r.is_seasoning} for r in results]

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
        
        new_item = models.Item(
            name=data['name'], 
            expiry_date=expiry,
            user_id=current_user 
        )
        db.add(new_item)
        db.commit()
        return {"message": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="저장 실패")

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
# 레시피 및 즐겨찾기 연동
# ---------------------------------------------------------
@app.get("/api/recipes")
def get_recipes(db: Session = Depends(get_db), current_user: str = Depends(get_current_user_id)):
    try:
        recipes = db.query(models.Recipe).all()
        all_ingredients = db.query(models.RecipeIngredient).all()
        
        user_favorites = db.query(models.Favorite.recipe_id).filter(
            models.Favorite.user_id == current_user
        ).all()
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
                "favorite": r.recipe_id in favorite_recipe_ids,
                "image_url": r.image_url or "",
                "instructions": r.instructions or "", 
                "original_ingredients": r.original_ingredients or ""
            })
        return results
    except Exception as e:
        import traceback
        traceback.print_exc() 
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/recipes/{recipe_id}/favorite")
async def update_favorite(recipe_id: int, request: Request, db: Session = Depends(get_db), current_user: str = Depends(get_current_user_id)):
    try:
        data = await request.json()
        is_favorite = data.get("favorite") 
        
        favorite_record = db.query(models.Favorite).filter(
            models.Favorite.recipe_id == recipe_id,
            models.Favorite.user_id == current_user
        ).first()
        
        if is_favorite:
            if not favorite_record:
                new_favorite = models.Favorite(user_id=current_user, recipe_id=recipe_id)
                db.add(new_favorite)
        else:
            if favorite_record:
                db.delete(favorite_record)
                
        db.commit()
        return {"message": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="실패")

# ---------------------------------------------------------
# 내 정보 수정 및 로그아웃
# ---------------------------------------------------------
@app.get("/profile")
def profile_page(request: Request, db: Session = Depends(get_db), current_user_id: int = Depends(get_optional_user_id)):
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)
    user = db.query(User).filter(User.id == current_user_id).first()
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})

@app.post("/update-profile")
def update_profile(
    current_pw: str = Form(None),
    new_pw: str = Form(None),
    new_pw_confirm: str = Form(None),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_optional_user_id)
):
    if not current_user_id:
        return RedirectResponse(url="/", status_code=303)

    user = db.query(models.User).filter(models.User.id == current_user_id).first()

    if current_pw and new_pw and new_pw_confirm:
        if not pwd_context.verify(current_pw, user.hashed_password):
            return JSONResponse(content={"status": "error", "message": "현재 비밀번호가 틀렸습니다!"})
        if new_pw != new_pw_confirm:
            return JSONResponse(content={"status": "error", "message": "새 비밀번호가 서로 일치하지 않습니다!"})
        if current_pw == new_pw:
            return JSONResponse(content={"status": "error", "message": "새 비밀번호는 현재 비밀번호와 달라야 합니다!"})
        if not (8 <= len(new_pw) <= 14):
            return JSONResponse(content={"status": "error", "message": "새 비밀번호는 8~14글자로 해주세요!"})
            
        has_letter = any(c.isalpha() for c in new_pw)
        has_number = any(c.isdigit() for c in new_pw)
        has_special = any(not c.isalnum() for c in new_pw)
        
        if (has_letter + has_number + has_special) < 2:
            return JSONResponse(content={"status": "error", "message": "새 비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 조합해주세요!"})
            
        user.hashed_password = get_password_hash(new_pw)
        db.commit()
        return JSONResponse(content={"status": "success"})

    return JSONResponse(content={"status": "error", "message": "비밀번호 변경 칸을 모두 입력해주세요!"})

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id", path="/")
    return response

@app.post("/withdraw")
def withdraw_account(db: Session = Depends(get_db), current_user_id: int = Depends(get_optional_user_id)):
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    db.delete(user)
    db.commit()

    response = HTMLResponse("""
        <script>
            alert('회원 탈퇴가 완료되었습니다. 그동안 이용해주셔서 감사합니다.');
            window.location.href = '/'; 
        </script>
    """)
    response.delete_cookie("user_id") 
    return response

# ---------------------------------------------------------
# 📸 영수증 스캔 (네이버 OCR 연동 API)
# ---------------------------------------------------------
@app.post("/scan_receipt")
async def scan_receipt(receipt: UploadFile = File(...)):
    invoke_url = os.getenv("OCR_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")

    if not invoke_url or not secret_key:
        print("⚠️ 네이버 OCR 키가 없습니다! 가짜 데이터로 테스트를 진행합니다.")
        time.sleep(1.5)
        mock_data = [
            {"name": "삼겹살", "expiry_date": "2026-04-12"},
            {"name": "대파", "expiry_date": "2026-04-12"},
            {"name": "깐마늘", "expiry_date": "2026-04-19"}
        ]
        return JSONResponse(content={"status": "success", "items": mock_data})

    try:
        image_bytes = await receipt.read()
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        
        request_json = {
            'images': [{'format': 'png', 'name': 'receipt_scan', 'data': image_base64}],
            'requestId': str(uuid.uuid4()),
            'version': 'V2',
            'timestamp': int(round(time.time() * 1000))
        }

        headers = {
            'X-OCR-SECRET': secret_key,
            'Content-Type': 'application/json'
        }

        response = requests.post(invoke_url, headers=headers, json=request_json)
        result = response.json()
        
        parsed_items = []
        if 'images' in result and result['images']:
            receipt_result = result['images'][0].get('receipt', {}).get('result', {})
            sub_results = receipt_result.get('subResults', [])
            
            if sub_results:
                items = sub_results[0].get('items', [])
                default_expiry = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
                
                for item in items:
                    name_text = item.get('name', {}).get('text', '')
                    if name_text:
                        parsed_items.append({
                            "name": name_text.replace(" ", ""),
                            "expiry_date": default_expiry
                        })

        if not parsed_items:
            return JSONResponse(content={"error": "영수증 글자를 읽지 못했습니다."}, status_code=400)

        return JSONResponse(content={"status": "success", "items": parsed_items})

    except Exception as e:
        print(f"OCR 에러 발생: {e}")
        return JSONResponse(content={"error": "서버 통신 중 문제 발생"}, status_code=500)
