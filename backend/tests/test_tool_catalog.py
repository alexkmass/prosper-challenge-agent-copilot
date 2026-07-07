"""Fast tests for tool_catalog() and GET /api/tools/catalog."""

import pytest

from routes.tools import get_tool_catalog
from tools.registry import TOOL_REGISTRY, tool_catalog


def test_tool_catalog_matches_registry():
    catalog = tool_catalog()
    assert len(catalog) == len(TOOL_REGISTRY) == 6
    assert [e["key"] for e in catalog] == sorted(TOOL_REGISTRY)

    for entry in catalog:
        spec = TOOL_REGISTRY[entry["key"]]
        assert entry["label"] == spec.label
        assert entry["category"] == spec.category
        assert entry["default_function"] == spec.default_function
        assert entry["default_description"] == spec.default_description
        assert entry["default_properties"] == spec.default_properties
        assert entry["default_required"] == list(spec.default_required)


@pytest.mark.asyncio
async def test_get_tool_catalog_route():
    catalog = await get_tool_catalog()
    assert {e["key"] for e in catalog} == set(TOOL_REGISTRY)
