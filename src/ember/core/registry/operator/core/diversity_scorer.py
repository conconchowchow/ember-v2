from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List
from pydantic import BaseModel

from src.ember.core.registry.operator.base.operator_base import Operator

from src.ember.core.registry.prompt_signature.signatures import Signature

class DiversityScoringOperatorInputs(BaseModel):
    responses: List[str]

class DiversityScoringOperatorOutputs(BaseModel):
    responses: List[str]
    diversity_score: int

class DiversityScoringSignature(Signature):
    pass

class DiversityScoringOperator(Operator[DiversityScoringOperatorInputs, Dict[str, Any]]):
    pass