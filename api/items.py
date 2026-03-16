from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import Item

# 라우터 설정 (prefix를 붙여서 주소를 관리합니다)
router = APIRouter(prefix="/items", tags=["items"])

# 1. 재료 추가 API
@router.post("")
async def add_item(data: dict, db: Session = Depends(get_db)):
    if not data.get('name') or not data.get('date'):
        raise HTTPException(status_code=400, detail="데이터가 누락되었습니다.")
    
    new_item = Item(name=data['name'], date=data['date'])
    db.add(new_item)
    db.commit()
    return {"message": "success"}

# 2. 재료 삭제 API
@router.delete("/{item_name}")
async def delete_item(item_name: str, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.name == item_name).first()
    if not item:
        raise HTTPException(status_code=404, detail="아이템을 찾을 수 없습니다.")
    
    db.delete(item)
    db.commit()
    return {"message": "deleted"}