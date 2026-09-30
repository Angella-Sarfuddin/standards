from sqlalchemy import Column, Integer, String
from database import Base


class SDOClassification(Base):
    __tablename__ = "sdo_classifications"

    id = Column(Integer, primary_key=True)

    sdo_id = Column(Integer)

    agency = Column(String(255))
    classification_code = Column(String(255))
    description = Column(String(355))

    parent_id = Column(Integer)
    status = Column(Integer)