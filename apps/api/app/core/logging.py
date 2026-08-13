import json
import logging
from datetime import UTC, datetime
from typing import Any, cast


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields: object = getattr(record, "fields", None)
        if isinstance(fields, dict):
            typed_fields = cast(dict[object, object], fields)
            payload.update(
                {key: value for key, value in typed_fields.items() if isinstance(key, str)}
            )
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
