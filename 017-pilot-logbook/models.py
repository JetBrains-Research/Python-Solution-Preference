import re
from sqlalchemy import Column, Integer, String, Boolean, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Aircraft(Base):
    __tablename__ = "aircraft"

    id = Column(Integer, primary_key=True, index=True)
    registration = Column(String, nullable=False)
    registration_canonical = Column(String, nullable=False, unique=True, index=True)
    make_model = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Airplane, Rotorcraft, Glider
    aircraft_class = Column(String, nullable=False)  # SEL, SES, MEL, MES, Helicopter, Gyroplane, Glider
    type_designator = Column(String, nullable=True)
    type_rating_required = Column(Boolean, default=False)
    complex_ac = Column(Boolean, default=False)
    high_performance = Column(Boolean, default=False)
    tailwheel = Column(Boolean, default=False)
    turbine = Column(Boolean, default=False)
    active = Column(Boolean, default=True)  # True = Active, False = Inactive

    flights = relationship("Flight", back_populates="aircraft")

    @staticmethod
    def canonical_registration(reg):
        if reg:
            return re.sub(r'[\s-]', '', reg).upper()
        return None

class Flight(Base):
    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, index=True)
    aircraft_id = Column(Integer, ForeignKey("aircraft.id"), nullable=False)
    date = Column(Date, nullable=False)
    departure = Column(String, nullable=False)
    arrival = Column(String, nullable=False)
    via = Column(String, nullable=True)
    total_time = Column(Float, nullable=False)
    day_time = Column(Float, nullable=True, default=0.0)
    night_time = Column(Float, nullable=True, default=0.0)
    pic = Column(Float, nullable=True, default=0.0)
    sic = Column(Float, nullable=True, default=0.0)
    dual_given = Column(Float, nullable=True, default=0.0)
    dual_received = Column(Float, nullable=True, default=0.0)
    cross_country = Column(Float, nullable=True, default=0.0)
    actual_instrument = Column(Float, nullable=True, default=0.0)
    simulated_instrument = Column(Float, nullable=True, default=0.0)
    day_takeoffs = Column(Integer, nullable=True, default=0)
    day_landings = Column(Integer, nullable=True, default=0)
    night_takeoffs = Column(Integer, nullable=True, default=0)
    night_landings = Column(Integer, nullable=True, default=0)
    instrument_approaches = Column(Integer, nullable=True, default=0)
    holds_performed = Column(Boolean, default=False)
    intercept_track = Column(Boolean, default=False)
    notes = Column(String, nullable=True)

    aircraft = relationship("Aircraft", back_populates="flights")
