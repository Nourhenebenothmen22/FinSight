"""Idempotent Garage v2 bucket and key permission initializer for FinSight."""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ADMIN_URL = os.environ.get("GARAGE_ADMIN_URL", "http://garage:3903").rstrip("/")
ADMIN_TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
ACCESS_KEY = os.environ["GARAGE_DEFAULT_ACCESS_KEY"]
BUCKETS = [
    b.strip()
    for b in os.environ.get("S3_BUCKETS", "finsight-documents,finsight-reports").split(",")
    if b.strip()
]


def api_request(method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
    """Execute an HTTP request against the Garage Admin API v2."""
    url = f"{ADMIN_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        try:
            return err.code, json.loads(body) if body else {}
        except json.JSONDecodeError:
            return err.code, body


def wait_for_garage(timeout_seconds: int = 45) -> None:
    """Wait until Garage Admin /health returns HTTP 200."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"{ADMIN_URL}/health", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Garage did not become healthy within {timeout_seconds}s at {ADMIN_URL}/health")


def ensure_bucket(bucket_name: str) -> str:
    """Ensure a bucket with globalAlias exists and return its ID."""
    query = urllib.parse.urlencode({"globalAlias": bucket_name})
    status, data = api_request("GET", f"/v2/GetBucketInfo?{query}")
    if status == 200 and isinstance(data, dict) and "id" in data:
        return str(data["id"])
    if status != 404:
        raise RuntimeError(f"Unexpected response checking bucket '{bucket_name}': HTTP {status} {data}")

    status, created = api_request("POST", "/v2/CreateBucket", {"globalAlias": bucket_name})
    if status != 200 or not isinstance(created, dict) or "id" not in created:
        raise RuntimeError(f"Failed creating bucket '{bucket_name}': HTTP {status} {created}")
    print(f"Created Garage bucket: {bucket_name} ({created['id']})")
    return str(created["id"])


def ensure_key_permissions(bucket_id: str, bucket_name: str) -> None:
    """Grant read/write/owner permissions to the application access key."""
    status, data = api_request(
        "POST",
        "/v2/AllowBucketKey",
        {
            "bucketId": bucket_id,
            "accessKeyId": ACCESS_KEY,
            "permissions": {"read": True, "write": True, "owner": True},
        },
    )
    if status != 200:
        raise RuntimeError(
            f"Failed granting permissions on '{bucket_name}' ({bucket_id}): HTTP {status} {data}"
        )


def main() -> int:
    """Initialize Garage buckets and access permissions."""
    wait_for_garage()

    # Verify default key exists
    key_query = urllib.parse.urlencode({"id": ACCESS_KEY})
    status, data = api_request("GET", f"/v2/GetKeyInfo?{key_query}")
    if status != 200:
        raise RuntimeError(f"Default Garage access key not found: HTTP {status} {data}")

    for bucket in BUCKETS:
        bucket_id = ensure_bucket(bucket)
        ensure_key_permissions(bucket_id, bucket)

    print(f"Garage initialization complete. Verified buckets: {', '.join(BUCKETS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
