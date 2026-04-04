from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime
from typing import Optional, List
import database.models as models
from database.connection import get_db
from sqlalchemy.orm import joinedload

app = FastAPI()

# HTML 및 정적 파일 경로 설정
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------
# 메인 페이지 (내 냉장고 목록 조회)
# ---------------------------------------------------------
@app.get("/")
def main_page(request: Request, db: Session = Depends(get_db)):
    try:
        items = db.query(models.Item).order_by(
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
        
        return templates.TemplateResponse("index.html", {"request": request, "items": processed_items})
    except Exception as e:
        print(f"메인 페이지 로드 에러: {e}")
        return templates.TemplateResponse("index.html", {"request": request, "items": [], "error": str(e)})

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
async def create_item(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        expiry_str = data.get('expiry_date')
        expiry = None
        if expiry_str and expiry_str.strip():
            try:
                expiry = datetime.strptime(expiry_str, '%Y-%m-%d').date()
            except ValueError:
                expiry = None 
        
        new_item = models.Item(name=data['name'], expiry_date=expiry)
        db.add(new_item)
        db.commit()
        return {"message": "success"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="저장 실패")

# ---------------------------------------------------------
# 소비기한 수정 및 삭제
# ---------------------------------------------------------
@app.post("/update-item/{item_name}")
async def update_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        new_date_str = data.get("expiry_date")
        item = db.query(models.Item).filter(models.Item.name == item_name).first()
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
def delete_item(item_name: str, db: Session = Depends(get_db)):
    try:
        item = db.query(models.Item).filter(models.Item.name == item_name).first()
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
def get_recipes(db: Session = Depends(get_db)):
    try:
        # 조인을 사용하여 레시피와 재료를 한 번에 쿼리
        recipes = db.query(models.Recipe).all()
        
        # 모든 재료 데이터를 한꺼번에 가져와서 메모리에서 매핑
        all_ingredients = db.query(models.RecipeIngredient).all()
        
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
                "favorite": bool(r.favorite),
                "image_url": r.image_url or "",
                "instructions": r.instructions or "", 
                "original_ingredients": r.original_ingredients or ""
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 즐겨찾기
@app.post("/api/recipes/{recipe_id}/favorite")
async def update_favorite(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        recipe = db.query(models.Recipe).filter(models.Recipe.recipe_id == recipe_id).first()
        if recipe:
            recipe.favorite = data.get("favorite")
            db.commit()
            return {"message": "success"}
        raise HTTPException(status_code=404, detail="레시피 없음")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="실패")