"""KG-Factory agents for knowledge graph construction."""

from agents.user_intent import UserIntentAgent
from agents.file_suggestion import FileSuggestionAgent
from agents.schema_proposal import SchemaProposalAgent
from agents.schema_critic import SchemaCriticAgent
from agents.ner_extraction import NerExtractionAgent
from agents.fact_extraction import FactExtractionAgent
from agents.competency_questions import CompetencyQuestionsAgent

__all__ = [
    "UserIntentAgent",
    "FileSuggestionAgent",
    "SchemaProposalAgent",
    "SchemaCriticAgent",
    "NerExtractionAgent",
    "FactExtractionAgent",
    "CompetencyQuestionsAgent",
]
