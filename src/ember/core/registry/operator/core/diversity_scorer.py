from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List
from pydantic import BaseModel

from src.ember.core.registry.operator.base.operator_base import Operator

from src.ember.core.registry.prompt_signature.signatures import Signature

from src.ember.core.utils.eval.evaluators import DiversityScoringEvaluator

class DiversityScoringOperatorInputs(BaseModel):
    responses: List[str]

#TODO: fix
class DiversityScoringOperatorOutputs(BaseModel):
    responses: List[str]
    diversity_score: int

class DiversityScoringOperator(Operator[DiversityScoringOperatorInputs, Dict[str, Any]]):
    def forward(self, *, inputs: DiversityScoringOperatorInputs) -> Dict[str, Any]:
        responses: List[Any] = inputs.model_dump()['responses'] 
        diversity_score: int = DiversityScoringEvaluator().evaluate()['score']
        return {"responses": responses, "divserity_score": diversity_score}
