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
from passlib.context import CryptContext

# 데이터베이스 관련 모듈 임포트
import database.models as models
from database.connection import get_db, engine

# ---------------------------------------------------------
# 보안 설정
# ---------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str):
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    return pwd_context.hash(pwd_bytes)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)

app = FastAPI()

# 서버 시작 시 테이블 자동 생성
models.Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# 인증 로직 (생략 없이 포함)
# ---------------------------------------------------------
@app.get("/")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_user(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "아이디/비밀번호 확인 필요"})
    
    response = RedirectResponse(url="/main", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id), httponly=True)
    return response

# ---------------------------------------------------------
# 메인 냉장고 (소비기한 및 D-Day 로직)
# ---------------------------------------------------------
@app.get("/main")
def main_page(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        return RedirectResponse(url="/", status_code=303)
    
    try:
        user_id = int(user_id_str)
        items = db.query(models.Item).filter(models.Item.user_id == user_id)\
            .order_by(
                models.Item.expiry_date.isnot(None).desc(), 
                models.Item.expiry_date.asc()
            ).all()
        today = datetime.now().date()
        processed_items = []
        for item in items:
            d_day = (item.expiry_date - today).days if item.expiry_date else None
            processed_items.append({
                "id": item.id, "name": item.name, "expiry_date": item.expiry_date, "d_day": d_day
            })
        return templates.TemplateResponse("index.html", {"request": request, "items": processed_items, "current_user": user_id})
    except:
        return RedirectResponse(url="/", status_code=303)

# ---------------------------------------------------------
# 소비기한 업데이트
# ---------------------------------------------------------
@app.post("/update-item/{item_name}")
async def update_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        raise HTTPException(status_code=401)
    
    try:
        user_id = int(user_id_str)
        data = await request.json()
        new_date_str = data.get("expiry_date")
        
        # 이름과 유저 식별자를 동시에 체크하여 본인의 아이템만 수정
        item = db.query(models.Item).filter(
            models.Item.name == item_name, 
            models.Item.user_id == user_id
        ).first()
        
        if item:
            if new_date_str and new_date_str.strip():
                item.expiry_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            else:
                item.expiry_date = None
            db.commit()
            return {"status": "success", "message": "날짜 수정 완료"}
        
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    except Exception as e:
        db.rollback()
        print(f"Update Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 재료 검색 및 추가
# ---------------------------------------------------------
@app.get("/items/search")
def search_ingredients(q: str = "", db: Session = Depends(get_db)):
    query = db.query(models.MasterIngredient)
    if not q or q == "popular":
        results = query.order_by(models.MasterIngredient.name.asc()).limit(100).all()
    else:
        results = query.filter(models.MasterIngredient.name.like(f"%{q}%")).order_by(models.MasterIngredient.name.asc()).all()
    return [{"name": r.name, "is_seasoning": r.is_seasoning} for r in results]

@app.post("/items")
async def create_item(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    data = await request.json()
    expiry = datetime.strptime(data['expiry_date'], '%Y-%m-%d').date() if data.get('expiry_date') else None
    
    new_item = models.Item(name=data['name'], expiry_date=expiry, user_id=int(user_id_str))
    db.add(new_item)
    db.commit()
    return {"message": "success"}

@app.delete("/items/{item_name}")
def delete_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        raise HTTPException(status_code=401)

    # 본인의 아이템만 삭제할 수 있도록 검증
    item = db.query(models.Item).filter(
        models.Item.name == item_name, 
        models.Item.user_id == int(user_id_str)
    ).first()
    
    if item:
        db.delete(item)
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")

# ---------------------------------------------------------
# 영수증 OCR
# ---------------------------------------------------------
@app.post("/scan_receipt")
async def scan_receipt(receipt: UploadFile = File(...)):
    invoke_url = os.getenv("OCR_URL")
    secret_key = os.getenv("OCR_SECRET_KEY")

    # API 설정이 없는 경우 Mock 데이터 반환
    if not invoke_url or not secret_key:
        time.sleep(1)
        mock_data = [
            {"name": "삼겹살", "expiry_date": (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')},
            {"name": "대파", "expiry_date": (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')}
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

        headers = {'X-OCR-SECRET': secret_key, 'Content-Type': 'application/json'}
        response = requests.post(invoke_url, headers=headers, json=request_json)
        result = response.json()
        
        parsed_items = []
        if 'images' in result and result['images']:
            receipt_res = result['images'][0].get('receipt', {}).get('result', {})
            sub_results = receipt_res.get('subResults', [])
            
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

        return JSONResponse(content={"status": "success", "items": parsed_items})
    except Exception:
        return JSONResponse(content={"error": "OCR 통신 에러"}, status_code=500)
    
# ---------------------------------------------------------
# 레시피 목록 가져오기 API
# ---------------------------------------------------------
@app.get("/api/recipes")
def get_recipes(request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    current_user_id = int(user_id_str) if user_id_str else None

    try:
        # DB 연결 확인용 로그
        all_raw_recipes = db.query(models.Recipe).all()
        print(f"DB에서 가져온 레시피 개수: {len(all_raw_recipes)}개")

        if not all_raw_recipes:
            print("DB에 레시피는 있으나 SQLAlchemy 모델이 데이터를 읽지 못함")
            return []

        # 즐겨찾기 목록 추출
        favorite_ids = set()
        if current_user_id:
            fav_query = db.query(models.Favorite.recipe_id).filter(
                models.Favorite.user_id == current_user_id
            ).all()
            favorite_ids = {f[0] for f in fav_query}

        results = []
        for r in all_raw_recipes:
            # 모델의 필드명(recipe_id)이 실제 DB와 맞는지 확인 필수
            rid = getattr(r, 'recipe_id', None) or getattr(r, 'id', None)
            
            # 해당 레시피의 재료들 가져오기
            ing_query = db.query(models.RecipeIngredient.ingredient_name).filter(
                models.RecipeIngredient.recipe_id == rid
            ).all()
            ingredients_list = [i[0] for i in ing_query]

            results.append({
                "id": rid,
                "name": r.name,
                "ingredients": ingredients_list,
                "favorite": rid in favorite_ids,
                "image_url": r.image_url or "",
                "instructions": r.instructions or "",
                "original_ingredients": r.original_ingredients or ""
            })
            
        return results

    except Exception as e:
        import traceback
        traceback.print_exc()
        return []

# ---------------------------------------------------------
# 기타 (즐겨찾기, 로그아웃)
# ---------------------------------------------------------
@app.post("/api/recipes/{recipe_id}/favorite")
async def toggle_favorite(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    user_id_str = request.cookies.get("user_id")
    if not user_id_str:
        raise HTTPException(status_code=401)
    
    data = await request.json()
    is_favorite = data.get("favorite")
    
    fav_record = db.query(models.Favorite).filter(
        models.Favorite.user_id == int(user_id_str),
        models.Favorite.recipe_id == recipe_id
    ).first()
    
    if is_favorite and not fav_record:
        db.add(models.Favorite(user_id=int(user_id_str), recipe_id=recipe_id))
    elif not is_favorite and fav_record:
        db.delete(fav_record)
    
    db.commit()
    return {"message": "success"}

@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id")
    return response

if __name__ == "__main__":
    import uvicorn
    # 5000번 포트로 구동 (HTML에서 API 호출 주소와 일치 확인)
    uvicorn.run(app, host="127.0.0.1", port=5000)