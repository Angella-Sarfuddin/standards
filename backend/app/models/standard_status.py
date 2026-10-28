from sqlalchemy import Column, Integer, String

from app.database.database import Base


class StandardStatus(Base):
    __tablename__ = "std_status"

    id = Column(Integer, primary_key=True)
    status = Column(String(255))
    std_show = Column(Integer)
    cart_show = Column(Integer)
