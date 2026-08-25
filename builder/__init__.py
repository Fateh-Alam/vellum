"""Study Builder domain, catalog, query, and recipe services."""

from .catalog import BuilderCatalog, CatalogFacet, build_catalog
from .models import (
    BuildRequest,
    BuildResult,
    BuilderDefinition,
    BuilderOrder,
    BuilderPreview,
    BuilderWorkflow,
    PreviewCard,
    StatePreset,
    StudyRecipe,
)
from .query import compile_builder_query
from .repository import StudyRecipeRepository
from .scope import DeckScopeNode, DeckTagScope, ScopedTagNode, TopicDeckScope

__all__ = (
    "BuildRequest",
    "BuildResult",
    "BuilderCatalog",
    "BuilderDefinition",
    "BuilderOrder",
    "BuilderPreview",
    "BuilderWorkflow",
    "CatalogFacet",
    "PreviewCard",
    "StatePreset",
    "StudyRecipe",
    "StudyRecipeRepository",
    "DeckScopeNode",
    "DeckTagScope",
    "ScopedTagNode",
    "TopicDeckScope",
    "build_catalog",
    "compile_builder_query",
)
