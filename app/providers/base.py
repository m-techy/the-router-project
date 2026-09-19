from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any
import httpx
from app.models import ChatCompletionRequest, ProviderSpec

class ProviderError(RuntimeError):
    def __init__(self,message:str,status_code:int|None=None):
        super().__init__(message); self.status_code=status_code

class ProviderAdapter(ABC):
    @abstractmethod
    async def chat(self,provider:ProviderSpec,model:str,request:ChatCompletionRequest)->tuple[dict[str,Any],httpx.Headers]:
        raise NotImplementedError
    @abstractmethod
    async def stream(self,provider:ProviderSpec,model:str,request:ChatCompletionRequest)->AsyncIterator[bytes]:
        raise NotImplementedError
