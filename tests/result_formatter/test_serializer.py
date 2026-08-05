"""Tests for `querymind.result_formatter.serializer.ResultFormatterSerializer`."""

from __future__ import annotations

import json

import yaml

from querymind.result_formatter.engine import ResultFormatterEngine
from querymind.result_formatter.models import BusinessAnswer
from querymind.result_formatter.serializer import ResultFormatterSerializer

from .conftest import make_column, make_execution_result, make_query_result


def _answer() -> BusinessAnswer:
    query_result = make_query_result(
        (make_column("customer_id"), make_column("first_name", python_type="str")),
        ((1, "Alice"),),
    )
    execution_result = make_execution_result(
        "SELECT customer_id, first_name FROM customers WHERE customer_id = 1;", query_result
    )
    return ResultFormatterEngine().format(execution_result)


class TestToDict:
    def test_returns_json_safe_primitives(self) -> None:
        data = ResultFormatterSerializer.to_dict(_answer())
        assert data["answer_type"] == "detail"
        assert isinstance(data["formatted_table"]["rows"], list)


class TestToJson:
    def test_round_trips_through_json(self) -> None:
        text = ResultFormatterSerializer.to_json(_answer())
        parsed = json.loads(text)
        assert parsed["summary"]["row_count"] == 1

    def test_indent_is_honored(self) -> None:
        text = ResultFormatterSerializer.to_json(_answer(), indent=None)
        assert "\n" not in text


class TestToYaml:
    def test_round_trips_through_yaml(self) -> None:
        text = ResultFormatterSerializer.to_yaml(_answer())
        parsed = yaml.safe_load(text)
        assert parsed["answer_type"] == "detail"
