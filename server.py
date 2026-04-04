from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime
from typing import Optional, List
import database.models as models
from database.connection import get_db
from sqlalchemy.orm import joinedload
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from api.items import get_current_user_id, get_optional_user_id
from database.models import User
import re #이메일 형식 검사
from fastapi.responses import HTMLResponse #팝업창
from fastapi.responses import JSONResponse


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

app = FastAPI()

# HTML 및 정적 파일 경로 설정
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# 로그인 페이지 
# ---------------------------------------------------------
@app.get("/")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# ---------------------------------------------------------
# 로그인 처리 코드 추가
# ---------------------------------------------------------
@app.post("/login")
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. DB에서 아이디 찾기
    user = db.query(models.User).filter(models.User.username == username).first()
    
    # 2. 유저가 없거나 비밀번호가 틀리면 에러 반환
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            name="login.html", 
            context={"request": request, "error": "아이디나 비밀번호가 틀렸습니다."}
        )
    
    # 3. 로그인 성공! 메인 화면(/main)으로 보내면서 'user_id' 쿠키(입장권) 발급
    response = RedirectResponse(url="/main", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id))
    return response

# ---------------------------------------------------------
# 회원가입 페이지 
# ---------------------------------------------------------
@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# ---------------------------------------------------------
# # 회원가입 처리하기 (POST) 
# ---------------------------------------------------------
@app.post("/register")
def register_user(
    request: Request,
    username: str = Form(default=""), 
    password: str = Form(default=""), 
    password_confirm: str = Form(default=""),
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    
    errors = {} # 각 칸별 에러를 담을 주머니

    # 1. 아이디 글자 수 검사
    if not (6 <= len(username) <= 12):
        errors["username_error"] = "아이디는 6~12글자로 해주세요."
    else:
        # 아이디 길이가 정상이면 중복 검사 실행
        existing_user = db.query(models.User).filter(models.User.username == username).first()
        if existing_user:
            errors["username_error"] = "이미 존재하는 아이디입니다."

   # 2. 비밀번호 검사 (길이 + 조합 검사)
    if not (8 <= len(password) <= 14):
        errors["password_error"] = "비밀번호는 8~14글자로 해주세요."
    else:
        # 💡 영문, 숫자, 특수문자가 각각 포함되어 있는지 확인!
        has_letter = any(c.isalpha() for c in password)   # 영문자가 있는가?
        has_number = any(c.isdigit() for c in password)   # 숫자가 있는가?
        has_special = any(not c.isalnum() for c in password) # 특수문자가 있는가?
        
        # 3가지 조건 중 2가지 이상을 만족하지 못했다면 에러!
        if (has_letter + has_number + has_special) < 2:
            errors["password_error"] = "영문, 숫자, 특수문자 중 2가지 이상을 조합해주세요."

    # 3. 비밀번호 일치 검사
    if password != password_confirm:
        errors["confirm_error"] = "비밀번호가 다릅니다!!"
    # 4. 이메일 형식 검사 
    email_regex = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
    if not email_regex.match(email):
        errors["email_error"] = "올바른 이메일 형식을 입력해주세요."
    else:
        # 💡 [핵심] 형식이 올바를 때만 중복 검사를 진행합니다!
        existing_email = db.query(models.User).filter(models.User.email == email).first()
        if existing_email:
            errors["email_error"] = "이미 가입된 이메일입니다."

    # 🚨 에러가 하나라도 발생했다면 다시 가입 페이지로 돌려보냄
    if errors:
        return templates.TemplateResponse(
            name="register.html", 
            context={
                "request": request, 
                "errors": errors, 
                "username": username, # 입력했던 아이디 유지
                "email": email       # 입력했던 이메일 칸에 그대로 유지
            }
        )
    
    # 4. 모든 조건 통과 시 DB 저장
    hashed_pw = get_password_hash(password)
    new_user = models.User(username=username, hashed_password=hashed_pw,email=email)
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
        response = templates.TemplateResponse("index.html", {"request": request, "items": processed_items})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    except Exception as e:
        print(f"메인 페이지 로드 에러: {e}")
        
        # 💡 [핵심 2] 에러 났을 때: 여기서도 담아서 헤더 추가 후 return!
        response = templates.TemplateResponse("index.html", {"request": request, "items": [], "error": str(e)})
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
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user  # 이제 HTML에서 user.email로 접근 가능!
    })

# ---------------------------------------------------------
# 내 정보 수정
# ---------------------------------------------------------

@app.post("/update-profile")
def update_profile(
    current_pw: str = Form(None),
    new_pw: str = Form(None),
    new_pw_confirm: str = Form(None),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_optional_user_id)
):
    if not current_user_id:
        # 로그인 안 했다면 그냥 로그인 창으로 (이건 HTML Redirect가 맞음)
        return RedirectResponse(url="/", status_code=303)

    user = db.query(models.User).filter(models.User.id == current_user_id).first()

    # 칸을 세 개 다 채웠을 때만 검사 시작!
    # 칸을 세 개 다 채웠을 때만 검사 시작!
    if current_pw and new_pw and new_pw_confirm:
        
        # 🚨 [1순위 검사] 현재 비밀번호가 맞는지 가장 먼저 확인합니다! (틀리면 바로 에러 던지고 끝)
        if not pwd_context.verify(current_pw, user.hashed_password):
            return JSONResponse(content={"status": "error", "message": "현재 비밀번호가 틀렸습니다!"})

        # 🚨 [2순위 검사] 새 비밀번호와 '확인' 칸이 다를 때
        if new_pw != new_pw_confirm:
            return JSONResponse(content={"status": "error", "message": "새 비밀번호가 서로 일치하지 않습니다!"})

        # 🚨 [3순위 검사] 새 비밀번호를 현재 비밀번호랑 똑같이 썼을 때
        if current_pw == new_pw:
            return JSONResponse(content={"status": "error", "message": "새 비밀번호는 현재 비밀번호와 달라야 합니다!"})

        # 🚨 [4순위 검사] 새 비밀번호 길이 및 조합 검사
        if not (8 <= len(new_pw) <= 14):
            return JSONResponse(content={"status": "error", "message": "새 비밀번호는 8~14글자로 해주세요!"})
            
        has_letter = any(c.isalpha() for c in new_pw)
        has_number = any(c.isdigit() for c in new_pw)
        has_special = any(not c.isalnum() for c in new_pw)
        
        if (has_letter + has_number + has_special) < 2:
            return JSONResponse(content={"status": "error", "message": "새 비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 조합해주세요!"})
            
        # ✨ [모든 검사 통과!!] 제일 마지막에 안심하고 DB에 진짜로 저장합니다.
        user.hashed_password = get_password_hash(new_pw)
        db.commit()
        return JSONResponse(content={"status": "success"})

    # 빈칸이 하나라도 있는 채로 저장 버튼을 눌렀을 때
    return JSONResponse(content={"status": "error", "message": "비밀번호 변경 칸을 모두 입력해주세요!"})
    # 빈칸이 하나라도 있는 채로 저장 버튼을 눌렀을 때
    return JSONResponse(content={"status": "error", "message": "비밀번호 변경 칸을 모두 입력해주세요!"})
# ---------------------------------------------------------
# 로그아웃
# ---------------------------------------------------------
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
def withdraw_account(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_optional_user_id) # 질문자님의 유저 확인 함수에 맞게!
):
    if not current_user_id:
        return RedirectResponse(url="/login", status_code=303)

    # 1. DB에서 유저 찾아서 삭제하기
    user = db.query(models.User).filter(models.User.id == current_user_id).first()
    db.delete(user)
    db.commit()

    # 2. 성공 알림 띄우고 메인으로 쫓아내기
    response = HTMLResponse("""
        <script>
            alert('회원 탈퇴가 완료되었습니다. 그동안 이용해주셔서 감사합니다.');
            window.location.href = '/'; 
        </script>
    """)
    
    # 💡 탈퇴 시에도 'user_id' 쿠키를 확실하게 지워줍니다!
    response.delete_cookie("user_id") 
    
    return response
