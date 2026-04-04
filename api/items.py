import os
import requests
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# 프로젝트 구조에 맞춘 임포트
from database.connection import get_db
from database.models import Item
from api.constants import MY_CUSTOM_ITEMS

load_dotenv()
router = APIRouter(prefix="/items", tags=["items"])
API_KEY = os.getenv("API_KEY")

# 표준 재료 DB 로드 로직
STANDARD_INGREDIENTS = []

def load_standard_db():
    global STANDARD_INGREDIENTS
    if not API_KEY:
        print("API 키 없음: 완제품 리스트만 사용합니다.")
        STANDARD_INGREDIENTS = sorted(MY_CUSTOM_ITEMS)
        return

    url = f"http://211.237.50.150:7080/openapi/{API_KEY}/json/Grid_20150827000000000227_1/1/1000"
    
    try:
        r = requests.get(url, timeout=10)
        res_data = r.json()
        
        rows = res_data.get("Grid_20150827000000000227_1", {}).get("row", [])
        
        if not rows:
            print("API 응답은 성공했으나 데이터가 비어있습니다.")
            STANDARD_INGREDIENTS = sorted(MY_CUSTOM_ITEMS)
            return

        # 괄호 제거 로직
        api_names = [row['IRDNT_NM'].split('(')[0].strip() for row in rows if row.get('IRDNT_NM')]
        
        # 중복 제거 및 커스텀 아이템 합치기
        combined = list(set(api_names + MY_CUSTOM_ITEMS))
        # 빈 문자열 제거 후 가나다순 정렬
        STANDARD_INGREDIENTS = sorted([n for n in combined if n])
        
        print(f"총 {len(STANDARD_INGREDIENTS)}개의 재료 로드 완료")
        
    except Exception as e:
        print(f"API 로드 실패 (에러: {e})")
        STANDARD_INGREDIENTS = sorted(MY_CUSTOM_ITEMS)

# 서버 시작 시 재료 DB 구축
load_standard_db()

# API 경로 설정

# 재료 검색
@router.get("/search")
async def search_ingredient(keyword: str = Query(None)):
    if not keyword or not keyword.strip():
        # 검색어 없을 때 전체 리스트 반환
        return [{"name": name} for name in STANDARD_INGREDIENTS]
    
    clean_keyword = keyword.strip()
    # 포함 검색 방식
    results = [{"name": name} for name in STANDARD_INGREDIENTS if clean_keyword in name]
    return results

# 재료 추가 (DB 저장)
@router.post("")
async def add_to_fridge(item_data: dict, db: Session = Depends(get_db)):
    if not item_data.get("name"):
        raise HTTPException(status_code=400, detail="이름이 없습니다.")
    
    new_item = Item(
        name=item_data['name'],
        category=item_data['category'],
        expiry_date=item_data['expiry_date']
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return {"status": "success"}

# 재료 삭제 (DB 삭제)
@router.delete("/{name}")
async def delete_from_fridge(name: str, db: Session = Depends(get_db)):
    item_to_delete = db.query(Item).filter(Item.name == name).first()
    if item_to_delete:
        db.delete(item_to_delete)
        db.commit()
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")