from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.entities import LeadStatus

class LeadCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    property_type: str|None=None; address: str|None=None; municipality: str|None=None; district: str|None=None
    source_url: str|None=None; source_name: str|None=None; evidence: str|None=None
    owner_name: str|None=None; owner_email: EmailStr|None=None; owner_phone: str|None=None
    contact_confidence: str="unknown"; contact_source: str|None=None; lawful_basis: str|None=None
    outreach_allowed: bool=False; score: int=0; score_reason: str|None=None
    assigned_to: int|None=None; property_data: dict={}
class LeadOut(LeadCreate):
    model_config=ConfigDict(from_attributes=True)
    id:int; status:LeadStatus; created_at:datetime; updated_at:datetime
class LeadUpdate(BaseModel):
    status:LeadStatus|None=None; assigned_to:int|None=None; outreach_allowed:bool|None=None; lawful_basis:str|None=None
class FollowUpCreate(BaseModel):
    seller_id:int|None=None; due_at:datetime; note:str
class DraftCreate(BaseModel):
    recipient:EmailStr; subject:str; body:str
