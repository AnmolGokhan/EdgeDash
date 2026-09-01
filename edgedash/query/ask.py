"""Two-call natural-language query pipeline: route, execute, phrase."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import edgedash.storage as storage
from edgedash.config import load_config
from edgedash.llm import complete_json
from edgedash.query.tools import TOOLS


@dataclass(frozen=True)
class Answer:
    text: str
    rows: list[dict[str, Any]]
    tool_used: str | None
    params: dict[str, Any]


_ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": ["string", "null"]},
        "params": {"type": "object"},
        "confidence": {"type": "string", "enum": ["high", "low"]},
    },
    "required": ["tool", "params", "confidence"],
    "additionalProperties": False,
}
_PHRASE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def _routing_prompt(question: str) -> str:
    registry = "\n".join(
        f"- {name}: {item['description']} Parameters: {json.dumps(item['parameters'], sort_keys=True)}"
        for name, item in TOOLS.items()
    )
    return (
        f"Question:\n{question}\n\nAvailable tools:\n{registry}\n\n"
        "Choose a tool only when it directly answers the question. If no tool "
        "matches, return tool=null. Do not choose the closest tool. Do not "
        "generate SQL or access a database."
    )


def _unanswerable() -> Answer:
    descriptions = "; ".join(f"{name}: {item['description']}" for name, item in TOOLS.items())
    return Answer(f"That question cannot be answered by the available tools. You can ask: {descriptions}", [], None, {})


def _validate_params(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    spec = TOOLS[tool_name]["parameters"]
    unknown = set(params) - set(spec)
    if unknown:
        raise ValueError(f"Router supplied unknown parameter(s): {', '.join(sorted(unknown))}")
    validated: dict[str, Any] = {}
    for name, value in params.items():
        definition = spec[name]
        if definition.get("type") == "integer":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Parameter {name!r} must be an integer") from exc
            value = max(definition["minimum"], min(definition["maximum"], value))
        elif definition.get("type") == "string":
            if not isinstance(value, str):
                raise ValueError(f"Parameter {name!r} must be a string")
        validated[name] = value
    return validated


def ask(question: str) -> Answer:
    started = time.monotonic()
    tool_name: str | None = None
    params: dict[str, Any] = {}
    answerable = False
    try:
        route = complete_json(_routing_prompt(question), _ROUTE_SCHEMA)
        tool_name = route.get("tool")
        params = route.get("params") or {}
        if tool_name is None:
            return _unanswerable()
        if not isinstance(tool_name, str) or tool_name not in TOOLS:
            raise ValueError(f"Router selected unknown tool: {tool_name!r}")
        if not isinstance(params, dict):
            raise ValueError("Router params must be an object")
        params = _validate_params(tool_name, params)

        answerable = True
        result = TOOLS[tool_name]["function"](**params)
        rows = result.get("rows", [])
        summary = result.get("summary", "")
        phrase_prompt = (
            f"Question:\n{question}\n\nReturned rows:\n{json.dumps(rows, sort_keys=True)}\n\n"
            f"Summary:\n{summary}\n\n"
            "Write 2-3 sentences using only numbers present in these rows; do not "
            "estimate or add outside context. If the rows are empty say the data "
            "does not contain an answer."
        )
        phrased = complete_json(phrase_prompt, _PHRASE_SCHEMA)
        return Answer(str(phrased["text"]), rows, tool_name, params)
    finally:
        config = load_config()
        storage.init_db(config.db_path)
        storage.log_query(config.db_path, question, tool_name, params, answerable, time.monotonic() - started)