from sqlalchemy import Column, Integer, String
from database import Base


class StandardClassification(Base):
    __tablename__ = "bsbe_std_classifications"

    id = Column(Integer, primary_key=True)

    classfication_id = Column(Integer)
    standard_id = Column(Integer)
    sdo_id = Column(Integer)

    sdo = Column(String(45))
    status = Column(Integer)