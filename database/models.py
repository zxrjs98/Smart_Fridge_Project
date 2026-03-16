from sqlalchemy import Column, Integer, String
from .connection import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    date = Column(String(50))  # 소비기한