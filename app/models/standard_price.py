from sqlalchemy import Column, Integer, String, Numeric
from database import Base


class StandardPrice(Base):
    __tablename__ = "std_prices"

    id = Column(Integer, primary_key=True)

    std_id = Column(Integer)
    formate_id = Column(Integer)
    language_id = Column(Integer)

    member_price_rate = Column(Numeric(10, 2))
    non_member_price_rate = Column(Numeric(10, 2))

    sdo_id = Column(Integer)
    status = Column(Integer)

    ProductSKU = Column(String(100))