"""Dynamic DNS Server - API.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

https://github.com/foorensic/ddns-server
Copyright (C) 2024 foorensic
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import secrets
import tempfile
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import tomllib
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, constr

with Path("pyproject.toml").open("rb") as file_handle:
    project_toml = tomllib.load(file_handle)
    PROJECT_NAME = project_toml.get("tool", {}).get("poetry", {}).get("name", "")
    PROJECT_VERSION = project_toml.get("tool", {}).get("poetry", {}).get("version", "")

AUTH_USER = os.environ["AUTH_USER"]  # This intentionally
AUTH_PASS = os.environ["AUTH_PASS"]  # raises a KeyError
RECORD_TTL = os.environ.get("RECORD_TTL", "3600")
ZONE = os.environ.get("ZONE", "").strip(". ")
NSUPDATE = "/usr/bin/nsupdate"

logger = logging.getLogger("uvicorn.error")
security = HTTPBasic()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
router = APIRouter(prefix="/api/v1")


class ApiResponse(BaseModel):
    """Record update response model."""

    success: bool
    message: str


class RecordType(str, Enum):
    """Record type enum."""

    A = "A"
    TXT = "TXT"


class MethodType(str, Enum):
    """MethodType enum."""

    update = "update"
    delete = "delete"


HostType = constr(
    pattern=r"^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$",
)


def is_valid_ip(address: str) -> bool:
    """Validate IP address."""
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return False
    return True


def get_current_username(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    """Validate user and return username."""
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = AUTH_USER.encode("utf8")
    is_correct_username = secrets.compare_digest(current_username_bytes, correct_username_bytes)
    current_password_bytes = credentials.password.encode("utf8")
    correct_password_bytes = AUTH_PASS.encode("utf8")
    is_correct_password = secrets.compare_digest(current_password_bytes, correct_password_bytes)
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@router.get("/{record_type}/{method}", summary="Update/Delete Records", response_model=ApiResponse)
async def update_record(
    request: Request,
    username: Annotated[str, Depends(get_current_username)],  # noqa: ARG001
    record_type: RecordType,
    method: MethodType,
    host: Annotated[list[HostType], Query()],
    value: Annotated[str | None, Query()] = "",
) -> dict:
    """Update or delete a DNS record."""
    value = value.strip(" \"'") if value else ""
    record_value = ""

    if record_type == RecordType.A:
        # User provided IP?
        if value:
            if not is_valid_ip(value):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Value for A record is not a valid IP",
                )
            record_value = value
        else:
            record_value = request.client.host

    elif record_type == RecordType.TXT:
        if method == MethodType.update and not value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="TXT record value cannot be empty")
        if value:
            value = value.replace('"', '\\"')
            record_value = f'"{value}"'

    # Create the update file
    file_content = "server 127.0.0.1\n"
    file_content += f"zone {ZONE}\n"
    for record_host in host:
        file_content += f"update delete {record_host}.{ZONE} {record_type.value}\n"
        if method == MethodType.update:
            file_content += f"update add {record_host}.{ZONE} {RECORD_TTL} {record_type.value} {record_value}\n"
    file_content += "send\n"

    update_file = Path(tempfile.gettempdir()) / "nsupdate.txt"
    update_file.write_text(file_content, "utf-8")

    command = [NSUPDATE, update_file.as_posix()]
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
    except Exception:
        logger.exception("Failed running %s:", command)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occured.") from None

    if proc.returncode != 0:
        logger.error("Failed running %s (%s): stdout: %s, stderr: %s", command, proc.returncode, stdout, stderr)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occured.")

    message = f"Updated record: {host} {record_type.value} {record_value}"
    if method == MethodType.delete:
        message = f"Deleted record: {host} {record_type.value}"
    logger.info(message)
    return {"success": True, "message": message}


@router.get("/ip", summary="Client IP", response_class=PlainTextResponse)
def get_ip(request: Request) -> str:
    """Return client IP."""
    return request.client.host


@app.get("/docs", summary="OpenAPI Documentation", include_in_schema=False)
def get_documentation(username: str = Depends(get_current_username)) -> HTMLResponse:  # noqa: ARG001
    """Return Swagger OpenAPI documentation of this endpoint."""
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Dynamic DNS API")


@app.get("/openapi.json", summary="OpenAPI JSON", include_in_schema=False)
def openapi_json(username: str = Depends(get_current_username)) -> dict[str, Any]:  # noqa: ARG001
    """Return the OpenAPI JSON specification of this API."""
    return get_openapi(title=PROJECT_NAME, version=PROJECT_VERSION, routes=app.routes)


app.include_router(router)
