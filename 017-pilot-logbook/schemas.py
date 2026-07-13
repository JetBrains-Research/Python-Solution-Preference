from pydantic import BaseModel, Field, validator, field_validator, model_validator
from typing import Optional, List
from datetime import date, datetime
from enum import Enum

# ---------- Enums ----------
class CategoryEnum(str, Enum):
    airplane = "Airplane"
    rotorcraft = "Rotorcraft"
    glider = "Glider"

class ClassEnum(str, Enum):
    sel = "SEL"
    ses = "SES"
    mel = "MEL"
    mes = "MES"
    helicopter = "Helicopter"
    gyroplane = "Gyroplane"
    glider = "Glider"

# ---------- Aircraft ----------
class AircraftBase(BaseModel):
    registration: str
    make_model: str
    category: CategoryEnum
    aircraft_class: ClassEnum
    type_designator: Optional[str] = None
    type_rating_required: bool = False
    complex_ac: bool = False
    high_performance: bool = False
    tailwheel: bool = False
    turbine: bool = False

class AircraftCreate(AircraftBase):
    @field_validator('registration')
    @classmethod
    def registration_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('Registration is required')
        return v.strip()

    @model_validator(mode='after')
    def check_type_designator(self):
        if self.type_rating_required and (not self.type_designator):
            raise ValueError('Type designator required when type rating required is true')
        return self

class AircraftUpdate(BaseModel):
    registration: Optional[str] = None
    make_model: Optional[str] = None
    category: Optional[CategoryEnum] = None
    aircraft_class: Optional[ClassEnum] = None
    type_designator: Optional[str] = None
    type_rating_required: Optional[bool] = None
    complex_ac: Optional[bool] = None
    high_performance: Optional[bool] = None
    tailwheel: Optional[bool] = None
    turbine: Optional[bool] = None

    @field_validator('registration')
    @classmethod
    def registration_not_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Registration is required')
        return v.strip() if v else v

class AircraftResponse(AircraftBase):
    id: int
    active: bool

    class Config:
        from_attributes = True

# ---------- Flight ----------
class FlightBaseRead(BaseModel):
    date: date
    aircraft_id: int
    departure: str
    arrival: str
    via: Optional[str] = None
    total_time: float
    day_time: float = 0.0
    night_time: float = 0.0
    pic: float = 0.0
    sic: float = 0.0
    dual_given: float = 0.0
    dual_received: float = 0.0
    cross_country: float = 0.0
    actual_instrument: float = 0.0
    simulated_instrument: float = 0.0
    day_takeoffs: int = 0
    day_landings: int = 0
    night_takeoffs: int = 0
    night_landings: int = 0
    instrument_approaches: int = 0
    holds_performed: bool = False
    intercept_track: bool = False
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class FlightCreate(BaseModel):
    date: date
    aircraft_id: int
    departure: str
    arrival: str
    via: Optional[str] = None
    total_time: float
    day_time: float = 0.0
    night_time: float = 0.0
    pic: float = 0.0
    sic: float = 0.0
    dual_given: float = 0.0
    dual_received: float = 0.0
    cross_country: float = 0.0
    actual_instrument: float = 0.0
    simulated_instrument: float = 0.0
    day_takeoffs: int = 0
    day_landings: int = 0
    night_takeoffs: int = 0
    night_landings: int = 0
    instrument_approaches: int = 0
    holds_performed: bool = False
    intercept_track: bool = False
    notes: Optional[str] = None

    @field_validator('date')
    @classmethod
    def date_not_future(cls, v):
        if v > date.today():
            raise ValueError('Date cannot be in the future')
        return v

    @field_validator('total_time')
    @classmethod
    def total_time_positive(cls, v):
        if v <= 0:
            raise ValueError('Total Time must be > 0')
        return v

    @field_validator('total_time', 'day_time', 'night_time', 'pic', 'sic', 'dual_given', 'dual_received', 'cross_country', 'actual_instrument', 'simulated_instrument')
    @classmethod
    def time_multiples_of_tenth(cls, v):
        if v is not None:
            if abs((v * 10) % 1) > 1e-9 and abs((v * 10) % 1) < (1 - 1e-9):
                raise ValueError('Times must be in 0.1 hour increments')
        return v

    @field_validator('day_takeoffs', 'day_landings', 'night_takeoffs', 'night_landings', 'instrument_approaches')
    @classmethod
    def non_negative_int(cls, v):
        if v is not None and v < 0:
            raise ValueError('Counts must be non-negative integers')
        return v

    @model_validator(mode='after')
    def validate_times(self):
        if round(self.day_time + self.night_time, 10) != round(self.total_time, 10):
            raise ValueError('Day Time + Night Time must equal Total Time exactly')
        if round(self.actual_instrument + self.simulated_instrument, 10) > round(self.total_time, 10):
            raise ValueError('Actual Instrument + Simulated Instrument cannot exceed Total Time')
        if self.pic > 0 and self.sic > 0:
            raise ValueError('PIC and SIC cannot both be > 0')
        if self.pic + self.sic > self.total_time:
            raise ValueError('PIC + SIC cannot exceed Total Time')
        if self.dual_given > 0 and self.dual_received > 0:
            raise ValueError('Dual Given and Dual Received cannot both be > 0')
        if self.dual_given > self.total_time:
            raise ValueError('Dual Given cannot exceed Total Time')
        if self.dual_received > self.total_time:
            raise ValueError('Dual Received cannot exceed Total Time')
        if self.cross_country > self.total_time:
            raise ValueError('Cross-country cannot exceed Total Time')
        return self

class FlightUpdate(BaseModel):
    date: Optional[date] = None
    aircraft_id: Optional[int] = None
    departure: Optional[str] = None
    arrival: Optional[str] = None
    via: Optional[str] = None
    total_time: Optional[float] = None
    day_time: Optional[float] = None
    night_time: Optional[float] = None
    pic: Optional[float] = None
    sic: Optional[float] = None
    dual_given: Optional[float] = None
    dual_received: Optional[float] = None
    cross_country: Optional[float] = None
    actual_instrument: Optional[float] = None
    simulated_instrument: Optional[float] = None
    day_takeoffs: Optional[int] = None
    day_landings: Optional[int] = None
    night_takeoffs: Optional[int] = None
    night_landings: Optional[int] = None
    instrument_approaches: Optional[int] = None
    holds_performed: Optional[bool] = None
    intercept_track: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator('date')
    @classmethod
    def date_not_future(cls, v):
        if v is not None and v > date.today():
            raise ValueError('Date cannot be in the future')
        return v

    @field_validator('total_time')
    @classmethod
    def total_time_positive(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Total Time must be > 0')
        return v

class FlightResponse(FlightBaseRead):
    id: int

class FlightDetailResponse(FlightResponse):
    aircraft: AircraftResponse

# ---------- Analytics ----------
class TotalsRequest(BaseModel):
    preset: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    group_by: Optional[str] = "overall"
    filters: Optional[dict] = None

class CurrencyResponse(BaseModel):
    category: str
    aircraft_class: str
    type_designator: Optional[str] = None
    day_current: bool
    day_takeoffs: int
    day_landings: int
    night_current: bool
    night_takeoffs: int
    night_landings: int
    instrument_current: Optional[bool] = None
    instrument_approaches: Optional[int] = None
    holds_performed_any: Optional[bool] = None
    intercept_track_any: Optional[bool] = None
