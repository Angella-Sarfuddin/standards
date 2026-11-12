from sqlalchemy import Column, Integer, String

from app.database.database import Base


class StandardStatusCode(Base):
    __tablename__ = "std_status_code"

    Id = Column(Integer, primary_key=True)
    title = Column(String(255))
