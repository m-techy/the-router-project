from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

class TierType(str, Enum):
    PERSISTENT_FREE="persistent_free"
    PROMOTIONAL="promotional"
    TRIAL="trial"
    PAID="paid"
    UNKNOWN="unknown"

class CertificationState(str, Enum):
    ACTIVE="active"
    RETRY_LATER="retry_later"
    CONFIGURED="configured"
    QUARANTINE="quarantine"
    UNKNOWN="unknown"

class CapabilitySet(BaseModel):
    chat: bool=True
    streaming: bool=True
    tools: bool=False
    json_mode: bool=False
    vision: bool=False
    audio: bool=False
    embeddings: bool=False
    reasoning: bool=False
    coding: bool=True

class QuotaSpec(BaseModel):
    scope: Literal["key","account","project","organization","provider","ip","unknown"]="unknown"
    rpm:int|None=None
    rpd:int|None=None
    tpm:int|None=None
    tpd:int|None=None
    monthly_tokens:int|None=None
    monthly_requests:int|None=None
    monthly_credits_usd:float|None=None
    weekly_requests:int|None=None
    neurons_per_day:int|None=None
    reset_timezone:str|None=None
    reset_hour:int|None=None
    source:str|None=None

class ModelSpec(BaseModel):
    id:str
    label:str|None=None
    context:int|None=None
    quality:float=Field(default=.5,ge=0,le=1)
    capabilities:CapabilitySet=Field(default_factory=CapabilitySet)
    free:bool=True
    enabled:bool=True
    promotional_expires_at:str|None=None

class ProviderSpec(BaseModel):
    id:str
    name:str
    enabled:bool=True
    tier:TierType=TierType.UNKNOWN
    env_key:str|None=None
    base_url:str
    adapter:str="openai_compatible"
    auth:Literal["bearer","optional_bearer","none"]="bearer"
    model_prefix_strip:str|None=None
    priority:float=1.0
    confidence:Literal["high","medium","low"]="medium"
    verification:str|None=None
    docs_url:str|None=None
    signup_url:str|None=None
    notes:list[str]=Field(default_factory=list)
    quota:QuotaSpec=Field(default_factory=QuotaSpec)
    models:list[ModelSpec]=Field(default_factory=list)
    extra_headers:dict[str,str]=Field(default_factory=dict)

class RegistryFile(BaseModel):
    updated_at:str
    providers:list[ProviderSpec]

class ChatMessage(BaseModel):
    role:str
    content:Any
    name:str|None=None
    tool_calls:Any|None=None
    tool_call_id:str|None=None

class ChatCompletionRequest(BaseModel):
    model:str="free/auto"
    messages:list[ChatMessage]
    stream:bool=False
    temperature:float|None=None
    top_p:float|None=None
    max_tokens:int|None=None
    max_completion_tokens:int|None=None
    tools:Any|None=None
    tool_choice:Any|None=None
    response_format:Any|None=None
    seed:int|None=None
    stop:Any|None=None
    user:str|None=None
    metadata:dict[str,Any]|None=None
    model_config={"extra":"allow"}

class Candidate(BaseModel):
    provider_id:str
    model_id:str
    score:float
    reason:str
