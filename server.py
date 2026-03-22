from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime
from database import models
from database.connection import get_db, engine
import requests
from core.config import settings

app = FastAPI()

# HTML 템플릿 및 정적 파일 설정
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.post("/update-item/{item_name}")
async def update_item(item_name: str, request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        new_date_str = data.get("expiry_date")
        
        # 터미널 디버깅 로그: 이 메시지가 찍히면 성공입니다!
        print(f">>> [수정 요청 수신] 재료: {item_name}, 날짜: {new_date_str}")
        
        # DB에서 해당 이름의 아이템 찾기
        item = db.query(models.Item).filter(models.Item.name == item_name.strip()).first()
        
        if not item:
            print(f"!!! 에러: [{item_name}] 아이템을 DB에서 찾지 못함")
            return {"message": "item not found"}, 404
            
        # 날짜 업데이트 및 저장
        item.expiry_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        db.commit()
        
        print(f">>> [수정 완료] {item_name} 유통기한 변경 성공")
        return {"message": "success"}
        
    except Exception as e:
        print(f"서버 에러 발생: {str(e)}")
        return {"message": str(e)}, 500

# 1. 메인 페이지 (조회 및 정렬)
@app.get("/")
def main_page(request: Request, db: Session = Depends(get_db)):
    items = db.query(models.Item).all()
    today = datetime.now().date()
    
    processed_items = []
    for item in items:
        d_day = (item.expiry_date - today).days
        processed_items.append({
            "name": item.name,
            "category": item.category,
            "expiry_date": item.expiry_date,
            "d_day": d_day
        })
    
    # 유통기한 임박순 정렬
    processed_items.sort(key=lambda x: x['d_day'])
    
    return templates.TemplateResponse("index.html", {"request": request, "items": processed_items})

# 2. 재료 추가 (POST)
@app.post("/items")
async def create_item(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    new_item = models.Item(
        name=data['name'],
        category=data['category'],
        expiry_date=datetime.strptime(data['expiry_date'], '%Y-%m-%d').date()
    )
    db.add(new_item)
    db.commit()
    return {"message": "success"}

# 3. 재료 삭제 (DELETE)
@app.delete("/items/{item_name}")
def delete_item(item_name: str, db: Session = Depends(get_db)):
    item = db.query(models.Item).filter(models.Item.name == item_name).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "success"}
    raise HTTPException(status_code=404, detail="Item not found")

# 4. 재료 검색 (공공 API 연동)
@app.get("/items/search")
def search_ingredients(q: str = ""):
    API_KEY = settings.MAFRA_API_KEY # .env에서 가져온 키
    URL = f"http://openapi.foodsafetykorea.go.kr/api/{API_KEY}/I2790/json/1/20"
    
    if q:
        URL += f"/DESC_KOR={q}"
    
    try:
        response = requests.get(URL)
        data = response.json()
        
        if "I2790" in data and "row" in data["I2790"]:
            raw_items = data["I2790"]["row"]
            return [{"name": item["DESC_KOR"], "category": item.get("GROUP_NAME", "식재료")} for item in raw_items]
        return []
            
    except Exception as e:
        print(f"API 호출 오류: {e}")
        return []