
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime
from database import Base


class StandardMaster(Base):
    __tablename__ = "standards"

    id = Column(Integer, primary_key=True)

    Standard_id = Column(
        String(150),
        unique=True,
        nullable=False
    )

    sdo_id = Column(Integer, nullable=False)
    standardno = Column(String(100), nullable=False)

    standardyear = Column(SmallInteger)
    title = Column(String(1000))
    url = Column(String(1000))
    display_stdNo = Column(String(255))

    status_id = Column(Integer, nullable=False)
    status = Column(Integer)

    recent = Column(Integer)
    mostpopular = Column(Integer)
    featured = Column(Integer)

    archive = Column(Integer)
    BSBESales = Column(Integer)
    BSBInternal = Column(Integer)
    BSBSubscription = Column(Integer)
    DocumentAvailability = Column(Integer)

    created_at = Column(DateTime)
    updated_at = Column(DateTime)

