from __future__ import annotations
from pathlib import Path
import yaml
from .models import ProviderSpec, RegistryFile, TierType

class ProviderRegistry:
    def __init__(self,path:str|Path):
        self.path=Path(path); self.data=self._load()
    def _load(self)->RegistryFile:
        return RegistryFile.model_validate(yaml.safe_load(self.path.read_text(encoding="utf-8")))
    def reload(self)->RegistryFile:
        self.data=self._load(); return self.data
    @property
    def providers(self)->list[ProviderSpec]: return self.data.providers
    def get(self,provider_id:str)->ProviderSpec:
        for p in self.providers:
            if p.id==provider_id:return p
        raise KeyError(provider_id)
    def allowed_providers(self,*,allow_trial:bool,allow_promo:bool)->list[ProviderSpec]:
        out=[]
        for p in self.providers:
            if not p.enabled:continue
            if p.tier==TierType.PERSISTENT_FREE:out.append(p)
            elif p.tier==TierType.TRIAL and allow_trial:out.append(p)
            elif p.tier==TierType.PROMOTIONAL and allow_promo:out.append(p)
        return out
