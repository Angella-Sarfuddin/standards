from sqlalchemy import Column, Integer, String
from database import Base


class Standard(Base):
    __tablename__ = "standards_search"

    id = Column(Integer, primary_key=True)
    Standard_id = Column(String(50))
    sdo_id = Column(Integer)
    status_id = Column(Integer)
    standardno = Column(String(50))
    title = Column(String(256))
    url = Column(String(256))
    stdkeyword = Column(String(256))
    created_at = Column(String(50))
    updated_at = Column(String(50))
    display_stdNo = Column(String(50))
    search_query = Column(String(256))
    created_by = Column(String(50))
    updated_by = Column(String(50))
    status = Column(Integer)
    esales = Column(Integer)
    stdNo_normalized = Column(String(50))