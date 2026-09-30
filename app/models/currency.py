from sqlalchemy import Column, Integer, String

from database import Base


class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True)
    currency_title = Column(String(255))
    currency_code = Column(String(255))
    currency_symbol = Column(String(10))