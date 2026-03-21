from datetime import date
from sqlalchemy import Column, Integer, String, Date
from .connection import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50))
    expiry_date = Column(Date, index=True)

    @property
    def d_day(self):
        if self.expiry_date:
            return (self.expiry_date - date.today()).days
        return 0