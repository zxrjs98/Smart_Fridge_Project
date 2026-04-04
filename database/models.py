from datetime import date
from sqlalchemy import Column, Integer, String, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from .connection import Base

# User 테이블
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(100))
    items = relationship("Item", back_populates="owner")
    
    email = Column(String(255), unique=True, index=True, nullable=True)

# 실제 재료 테이블
class Item(Base):
    __tablename__ = "user_items"

    id = Column(Integer, primary_key=True, index=True) # id 
    name = Column(String(100), nullable=False) # 재료명
    expiry_date = Column(Date, index=True) #소비기한
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="items")
    
    @property
    def d_day(self):
        if self.expiry_date:
            return (self.expiry_date - date.today()).days
        return 0

# 마스터 재료 사전 테이블
class MasterIngredient(Base):
    __tablename__ = "master_ingredients"

    ing_id = Column(Integer, primary_key=True, index=True) # ing_id
    name = Column(String(50), unique=True, nullable=False) # 재료명
    is_seasoning = Column(Boolean, default=False) # 기본 양념 제외 필터용

class Recipe(Base):
    __tablename__ = "recipes"
    recipe_id = Column(Integer, primary_key=True, index=True) # recipe_id
    name = Column(String(255), nullable=False) # 레시피명
    image_url = Column(String(500), nullable=True) # 이미지 경로
    instructions = Column(Text, nullable=True) # 조리법
    original_ingredients = Column(Text, nullable=False) # 재료설명

class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, nullable=False) # Recipe.recipe_id와 매칭
    ingredient_name = Column(String(100), nullable=False)

class Favorite(Base):
    __tablename__ = "favorites"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    recipe_id = Column(Integer, ForeignKey("recipes.recipe_id"), primary_key=True)