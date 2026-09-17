import logging
import re
from urllib.parse import urlsplit, urlunsplit


def redact_source(value: str) -> str:
    if not value.lower().startswith(("rtsp://", "rtsps://")):
        return value
    parts = urlsplit(value)
    hostname = parts.hostname or ""
    if parts.port:
        hostname += f":{parts.port}"
    netloc = f"***:***@{hostname}" if parts.username or parts.password else hostname
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class SecretFilter(logging.Filter):
    _pattern = re.compile(r"(rtsp[s]?://)([^\s/@:]+)(?::[^\s/@]*)?@", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._pattern.sub(r"\1***:***@", str(record.msg))
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretFilter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s: %(message)s")

