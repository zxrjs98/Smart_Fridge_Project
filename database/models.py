from datetime import date
from sqlalchemy import Column, Integer, String, Date, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from .connection import Base

# 사용자 테이블
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    
    items = relationship("Item", back_populates="owner", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")

# 내 냉장고 재료
class Item(Base):
    __tablename__ = "user_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    expiry_date = Column(Date, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="items")

# 레시피 즐겨찾기
class Favorite(Base):
    __tablename__ = "favorites"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    recipe_id = Column(Integer, ForeignKey("recipes.recipe_id"), primary_key=True)
    
    user = relationship("User", back_populates="favorites")

# 레시피 마스터 데이터
class Recipe(Base):
    __tablename__ = "recipes"
    recipe_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    image_url = Column(String(500), nullable=True)
    instructions = Column(Text, nullable=True)
    original_ingredients = Column(Text, nullable=False)

# 레시피 재료 테이블
class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    id = Column(Integer, primary_key=True, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.recipe_id"))
    ingredient_name = Column(String(100), nullable=False)

# 재료 사전
class MasterIngredient(Base):
    __tablename__ = "master_ingredients"
    ing_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    is_seasoning = Column(Boolean, default=False)