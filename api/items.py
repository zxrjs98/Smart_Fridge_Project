import os
import requests
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# DB 관련 임포트 (경로를 팀장님 프로젝트 구조에 맞췄습니다)
from database.connection import get_db
from database.models import Item
from api.constants import MY_CUSTOM_ITEMS

load_dotenv()
router = APIRouter(prefix="/items", tags=["items"])
MAFRA_API_KEY = os.getenv("MAFRA_API_KEY")

# --- 1. 표준 재료 DB 로드 로직 (기존과 동일) ---
STANDARD_INGREDIENTS = []

def load_standard_db():
    global STANDARD_INGREDIENTS
    if not MAFRA_API_KEY:
        STANDARD_INGREDIENTS = sorted(MY_CUSTOM_ITEMS)
        return
    url = f"http://211.237.50.150:7080/openapi/{MAFRA_API_KEY}/json/Grid_20150827000000000227_1/1/1000"
    try:
        r = requests.get(url, timeout=5)
        rows = r.json().get("Grid_20150827000000000227_1", {}).get("row", [])
        api_names = [row['IRDNT_NM'] for row in rows if row.get('IRDNT_NM')]
        STANDARD_INGREDIENTS = sorted(list(set(api_names + MY_CUSTOM_ITEMS)))
    except:
        STANDARD_INGREDIENTS = sorted(MY_CUSTOM_ITEMS)

load_standard_db()

# --- 2. API 경로 설정 (DB 연동 버전) ---

# 🔍 재료 검색
@router.get("/search")
async def search_ingredient(keyword: str = Query(...)):
    keyword = keyword.strip()
    if not keyword: return []
    return [{"name": name} for name in STANDARD_INGREDIENTS if name.startswith(keyword)]

# ➕ 재료 추가 (DB에 저장)
@router.post("")
async def add_to_fridge(item_data: dict, db: Session = Depends(get_db)):
    if not item_data.get("name"):
        raise HTTPException(status_code=400, detail="이름이 없습니다.")
    
    # DB 모델 객체 생성
    new_item = Item(
        name=item_data['name'],
        category=item_data['category'],
        expiry_date=item_data['expiry_date']
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    print(f"📥 DB 추가 완료: {new_item.name}")
    return {"status": "success"}

# 🗑️ 재료 삭제 (DB에서 삭제)
@router.delete("/{name}")
async def delete_from_fridge(name: str, db: Session = Depends(get_db)):
    # DB에서 해당 이름을 가진 첫 번째 아이템 검색
    item_to_delete = db.query(Item).filter(Item.name == name).first()
    
    if item_to_delete:
        db.delete(item_to_delete)
        db.commit()
        print(f"🗑️ DB 삭제 완료: {name}")
        return {"status": "success"}
    else:
        # DB에 없을 때 404 에러 반환
        raise HTTPException(status_code=404, detail=f"'{name}' 항목을 찾을 수 없습니다.")