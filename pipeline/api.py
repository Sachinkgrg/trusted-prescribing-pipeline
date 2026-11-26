"""A small client for the NHSBSA Open Data Portal API.

The portal runs on CKAN. We use two actions:
  package_show          lists the monthly files (resources) in a dataset
  datastore_search_sql  runs a read-only SQL query against one resource

Official example code: github.com/nhsbsa-data-analytics/open-data-portal-api
"""

import gzip
import time
from pathlib import Path

import requests


class ApiError(Exception):
    """The API could not give us a usable answer."""


class NhsbsaApi:
    def __init__(self, base_url: str, timeout_seconds: int = 120, retries: int = 3):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout_seconds
        self.retries = retries
        self.session = requests.Session()

    def _get(self, action: str, params: dict) -> dict:
        """Call one API action.

        Network problems and server errors (5xx) are retried, waiting longer
        each time. A rejected request (4xx, e.g. bad SQL) is not retried,
        because sending the same thing again gives the same answer. Instead
        we show the portal's own explanation.
        """
        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(
                    self.base_url + action, params=params, timeout=self.timeout
                )
            except requests.RequestException as error:
                last_error = error
                time.sleep(2 * attempt)
                continue

            status = getattr(response, "status_code", 200)
            if 400 <= status < 500:
                raise ApiError(f"{action} was rejected ({status}): {_explain(response)}")
            if status >= 500:
                last_error = f"server error {status}: {_explain(response)}"
                time.sleep(2 * attempt)
                continue

            try:
                payload = response.json()
            except ValueError:
                raise ApiError(f"{action} did not return JSON: {_explain(response)}")
            if not payload.get("success", False):
                raise ApiError(f"{action} failed: {payload.get('error')}")
            return payload["result"]
        raise ApiError(f"{action} failed after {self.retries} attempts: {last_error}")

    def list_resources(self, dataset_id: str) -> list[str]:
        """Names of every monthly resource in a dataset, e.g. EPD_202401."""
        result = self._get("package_show", {"id": dataset_id})
        return [resource["name"] for resource in result["resources"]]

    def run_sql(self, resource: str, sql: str) -> dict:
        """Run SQL against one resource.

        Returns {"records": [...]} for normal results, or
        {"download_urls": [...]} when the portal says the result was too
        large to send inline and gives links to CSV files instead.
        """
        result = self._get("datastore_search_sql", {"resource_id": resource, "sql": sql})
        inner = result.get("result", result)

        truncated = str(result.get("records_truncated", "false")).lower() == "true"
        if truncated and result.get("gc_urls"):
            return {"download_urls": [item["url"] for item in result["gc_urls"]]}

        return {"records": inner.get("records", [])}

    def count_rows(self, resource: str, where: str) -> int:
        """Ask the API how many rows match, so we can check what we loaded."""
        sql = f"SELECT COUNT(*) AS row_count FROM `{resource}` WHERE {where}"
        records = self.run_sql(resource, sql).get("records", [])
        if not records:
            raise ApiError(f"Count query returned nothing for {resource}")
        return int(next(iter(records[0].values())))

    def download(self, url: str, target: Path) -> None:
        """Save a CSV download link to disk, unzipping it if needed."""
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        content = response.content
        if content[:2] == b"\x1f\x8b":  # gzip files always start with these bytes
            content = gzip.decompress(content)
        target.write_bytes(content)


def _explain(response) -> str:
    """The portal's own error message, or the start of the raw reply."""
    try:
        error = response.json().get("error")
        if error:
            return str(error)
    except (ValueError, AttributeError):
        pass
    return (getattr(response, "text", "") or "")[:500]


def find_resource(resource_names: list[str], month: str) -> str | None:
    """Pick the resource for a month. Names end in YYYYMM, e.g. EPD_202401."""
    matches = [name for name in resource_names if name.endswith(month)]
    if len(matches) > 1:
        raise ApiError(f"More than one resource matches {month}: {matches}")
    return matches[0] if matches else None
