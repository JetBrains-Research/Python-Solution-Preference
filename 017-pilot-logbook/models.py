from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List, Dict, Any, Union
from datetime import date, datetime
from enum import Enum

class AircraftCategory(str, Enum):
    AIRPLANE = "Airplane"
    ROTORCRAFT = "Rotorcraft"
    GLIDER = "Glider"

class AircraftClass(str, Enum):
    SEL = "SEL"
    SES = "SES"
    MEL = "MEL"
    MES = "MES"
    HELICOPTER = "Helicopter"
    GYROPLANE = "Gyroplane"
    GLIDER = "Glider"

# Validation for category/class combinations
VALID_CATEGORY_CLASSES = {
    AircraftCategory.AIRPLANE: [AircraftClass.SEL, AircraftClass.SES, AircraftClass.MEL, AircraftClass.MES],
    AircraftCategory.ROTORCRAFT: [AircraftClass.HELICOPTER, AircraftClass.GYROPLANE],
    AircraftCategory.GLIDER: [AircraftClass.GLIDER],
}

class AircraftBase(BaseModel):
    registration: str = Field(..., min_length=1, description="Registration/Tail No.")
    make_model: str = Field(..., min_length=1, description="Make/Model")
    category: AircraftCategory
    class_: AircraftClass = Field(..., alias="class")
    type_designator: Optional[str] = None
    type_rating_required: bool = False
    is_complex: bool = False
    is_high_performance: bool = False
    is_tailwheel: bool = False
    is_turbine: bool = False

    @validator('class_', pre=True, always=True)
    def validate_category_class(cls, v, values):
        if 'category' in values:
            category = values['category']
            if v not in VALID_CATEGORY_CLASSES.get(category, []):
                raise ValueError(f'Class {v} is not valid for category {category}')
        return v

    @validator('type_designator')
    def validate_type_designator(cls, v, values):
        if values.get('type_rating_required', False) and not v:
            raise ValueError('Type Designator is required when Type rating required is true')
        return v

class AircraftCreate(AircraftBase):
    pass

class AircraftUpdate(BaseModel):
    registration: Optional[str] = None
    make_model: Optional[str] = None
    category: Optional[AircraftCategory] = None
    class_: Optional[AircraftClass] = Field(None, alias="class")
    type_designator: Optional[str] = None
    type_rating_required: Optional[bool] = None
    is_complex: Optional[bool] = None
    is_high_performance: Optional[bool] = None
    is_tailwheel: Optional[bool] = None
    is_turbine: Optional[bool] = None
    is_active: Optional[bool] = None

    @validator('class_', pre=True, always=True)
    def validate_category_class(cls, v, values):
        if v is not None and 'category' in values and values['category'] is not None:
            if v not in VALID_CATEGORY_CLASSES.get(values['category'], []):
                raise ValueError(f'Class {v} is not valid for category {values[category]}')
        return v

    @validator('type_designator')
    def validate_type_designator(cls, v, values):
        if values.get('type_rating_required', False) and not v:
            raise ValueError('Type Designator is required when Type rating required is true')
        return v

class AircraftResponse(AircraftBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class FlightBase(BaseModel):
    date: date
    departure: str = Field(..., min_length=1)
    arrival: str = Field(..., min_length=1)
    via: Optional[str] = None
    total_time: float = Field(..., gt=0, description="Total Time in hours")
    day_time: float = 0.0
    night_time: float = 0.0
    pic_time: float = 0.0
    sic_time: float = 0.0
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
    intercept_track_performed: bool = False
    notes: Optional[str] = None

    @validator('date')
    def validate_date(cls, v):
        today = date.today()
        if v > today:
            raise ValueError('Date cannot be in the future')
        return v

    @validator('total_time', 'day_time', 'night_time', 'pic_time', 'sic_time', 'dual_given', 'dual_received', 'cross_country', 'actual_instrument', 'simulated_instrument')
    def validate_time_increment(cls, v):
        if v < 0:
            raise ValueError('Time cannot be negative')
        if round(v * 10) != v * 10:
            raise ValueError('Time must be in 0.1 hour increments')
        return v

    @validator('day_takeoffs', 'day_landings', 'night_takeoffs', 'night_landings', 'instrument_approaches')
    def validate_non_negative(cls, v):
        if v < 0:
            raise ValueError('Count cannot be negative')
        return v

    @model_validator(mode='after')
    def validate_time_relationships(cls, values):
        day_time = values.day_time
        night_time = values.night_time
        total_time = values.total_time

        if round(day_time + night_time, 1) != round(total_time, 1):
            raise ValueError('Day Time + Night Time must equal Total Time')

        if values.actual_instrument + values.simulated_instrument > total_time + 0.001:
            raise ValueError('Actual Instrument + Simulated Instrument cannot exceed Total Time')

        if values.pic_time > 0 and values.sic_time > 0:
            raise ValueError('PIC and SIC cannot both be greater than 0')
        if values.pic_time + values.sic_time > total_time + 0.001:
            raise ValueError('PIC + SIC cannot exceed Total Time')

        if values.dual_given > 0 and values.dual_received > 0:
            raise ValueError('Dual Given and Dual Received cannot both be greater than 0')
        if values.dual_given > total_time + 0.001:
            raise ValueError('Dual Given cannot exceed Total Time')
        if values.dual_received > total_time + 0.001:
            raise ValueError('Dual Received cannot exceed Total Time')

        if values.cross_country > total_time + 0.001:
            raise ValueError('Cross-country cannot exceed Total Time')

        return values

class FlightCreate(FlightBase):
    aircraft_id: int = Field(..., description="ID of the aircraft for this flight")

class FlightUpdate(BaseModel):
    date: Optional[date] = None
    aircraft_id: Optional[int] = None
    departure: Optional[str] = None
    arrival: Optional[str] = None
    via: Optional[str] = None
    total_time: Optional[float] = None
    day_time: Optional[float] = None
    night_time: Optional[float] = None
    pic_time: Optional[float] = None
    sic_time: Optional[float] = None
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
    intercept_track_performed: Optional[bool] = None
    notes: Optional[str] = None

    @validator('date')
    def validate_date(cls, v):
        if v is not None:
            today = date.today()
            if v > today:
                raise ValueError('Date cannot be in the future')
        return v

    @validator('total_time', 'day_time', 'night_time', 'pic_time', 'sic_time', 'dual_given', 'dual_received', 'cross_country', 'actual_instrument', 'simulated_instrument')
    def validate_time_increment(cls, v):
        if v is not None:
            if v < 0:
                raise ValueError('Time cannot be negative')
            if round(v * 10) != v * 10:
                raise ValueError('Time must be in 0.1 hour increments')
        return v

    @validator('day_takeoffs', 'day_landings', 'night_takeoffs', 'night_landings', 'instrument_approaches')
    def validate_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError('Count cannot be negative')
        return v

    @model_validator(mode='after')
    def validate_time_relationships(cls, values):
        # Only validate if we have all the needed fields
        if (hasattr(values, 'day_time') and hasattr(values, 'night_time') and hasattr(values, 'total_time') and
            values.day_time is not None and values.night_time is not None and values.total_time is not None):
            if round(values.day_time + values.night_time, 1) != round(values.total_time, 1):
                raise ValueError('Day Time + Night Time must equal Total Time')

            if (hasattr(values, 'actual_instrument') and hasattr(values, 'simulated_instrument') and
                values.actual_instrument is not None and values.simulated_instrument is not None):
                if values.actual_instrument + values.simulated_instrument > values.total_time + 0.001:
                    raise ValueError('Actual Instrument + Simulated Instrument cannot exceed Total Time')

            if (hasattr(values, 'pic_time') and hasattr(values, 'sic_time') and
                values.pic_time is not None and values.sic_time is not None):
                if values.pic_time > 0 and values.sic_time > 0:
                    raise ValueError('PIC and SIC cannot both be greater than 0')
                if values.pic_time + values.sic_time > values.total_time + 0.001:
                    raise ValueError('PIC + SIC cannot exceed Total Time')

        return values

class FlightResponse(FlightBase):
    id: int
    aircraft_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat()
        }

class FlightListResponse(BaseModel):
    flights: List[FlightResponse]
    total: int

class FilterParams(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    aircraft_ids: Optional[List[int]] = None
    categories: Optional[List[AircraftCategory]] = None
    classes: Optional[List[AircraftClass]] = None
    search_text: Optional[str] = None

class AnalyticsTimeRange(str, Enum):
    LAST_90_DAYS = "last_90_days"
    LAST_6_MONTHS = "last_6_months"
    LAST_12_MONTHS = "last_12_months"
    CUSTOM = "custom"

class AnalyticsParams(BaseModel):
    time_range: AnalyticsTimeRange = AnalyticsTimeRange.LAST_90_DAYS
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    group_by: Optional[str] = None  # "category_class", "make_model", or None for overall
    aircraft_ids: Optional[List[int]] = None
    categories: Optional[List[AircraftCategory]] = None
    classes: Optional[List[AircraftClass]] = None

    @model_validator(mode='after')
    def validate_time_range(cls, values):
        if values.time_range == AnalyticsTimeRange.CUSTOM:
            if not values.start_date or not values.end_date:
                raise ValueError('start_date and end_date are required for custom time range')
        return values

class TotalsResponse(BaseModel):
    total_time: float = 0.0
    pic_time: float = 0.0
    sic_time: float = 0.0
    night_time: float = 0.0
    actual_instrument: float = 0.0
    simulated_instrument: float = 0.0
    cross_country: float = 0.0
    instrument_approaches: int = 0
    day_takeoffs: int = 0
    day_landings: int = 0
    night_takeoffs: int = 0
    night_landings: int = 0

class GroupedTotals(BaseModel):
    group_key: str
    totals: TotalsResponse

class AnalyticsResponse(BaseModel):
    time_range: str
    overall: TotalsResponse
    grouped: Optional[List[GroupedTotals]] = None

class DayNightCurrencyResponse(BaseModel):
    category: str
    class_: str
    type_designator: Optional[str] = None
    day_status: str
    day_takeoffs: int
    day_landings: int
    night_status: str
    night_takeoffs: int
    night_landings: int

class InstrumentCurrencyResponse(BaseModel):
    category: str
    status: str
    instrument_approaches: int
    holds_performed: bool
    intercept_track_performed: bool

class CurrencyResponse(BaseModel):
    day_night_currency: List[DayNightCurrencyResponse]
    instrument_currency: List[InstrumentCurrencyResponse]

class MessageResponse(BaseModel):
    message: str
