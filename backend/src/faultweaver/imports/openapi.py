from __future__ import annotations

import json
from copy import deepcopy
from urllib.parse import urlsplit

import yaml

from faultweaver.imports.canonical import DeclaredEndpoint, ParseResult, ParserLimits


class OpenApiParseError(ValueError):
    """Raised when an OpenAPI document cannot be imported safely."""


_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def parse_openapi(content: str, limits: ParserLimits) -> ParseResult:
    if len(content.encode("utf-8")) > limits.max_document_bytes:
        raise OpenApiParseError(
            f"OpenAPI document exceeds the {limits.max_document_bytes} byte limit"
        )
    document = _load_document(content)
    version = document.get("openapi")
    if not isinstance(version, str) or not (version.startswith("3.0") or version.startswith("3.1")):
        raise OpenApiParseError("OpenAPI 3.0 or 3.1 is required")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise OpenApiParseError("OpenAPI document requires a paths object")

    result = ParseResult()
    schemes = _security_schemes(document, result.warnings)
    root_servers = _servers(document.get("servers"), "document", result.warnings)
    operation_index = 0
    for raw_path, raw_path_item in paths.items():
        if not isinstance(raw_path, str) or not raw_path.startswith("/"):
            result.skipped_count += 1
            result.warnings.append("A malformed OpenAPI path was skipped")
            continue
        path_item = _resolve(raw_path_item, document, result.warnings, f"path {raw_path}")
        if not isinstance(path_item, dict):
            result.skipped_count += 1
            result.warnings.append(f"Path {raw_path}: path item is not an object")
            continue
        path_servers = _servers(path_item.get("servers"), f"path {raw_path}", result.warnings)
        for method, raw_operation in path_item.items():
            if method.lower() not in _METHODS:
                continue
            operation_index += 1
            if operation_index > limits.max_entries:
                raise OpenApiParseError(
                    f"OpenAPI contains more than {limits.max_entries} operations"
                )
            operation = _resolve(
                raw_operation, document, result.warnings, f"{method.upper()} {raw_path}"
            )
            if not isinstance(operation, dict):
                result.skipped_count += 1
                result.warnings.append(f"{method.upper()} {raw_path}: operation was skipped")
                continue
            operation_servers = _servers(
                operation.get("servers"), f"{method.upper()} {raw_path}", result.warnings
            )
            servers = operation_servers or path_servers or root_servers or [None]
            details = _operation_details(
                document,
                path_item,
                operation,
                schemes,
                method.upper(),
                raw_path,
                result.warnings,
            )
            for server_url in servers:
                result.endpoints.append(
                    DeclaredEndpoint(
                        method=method.upper(),
                        path_template=raw_path,
                        server_url=server_url,
                        details=deepcopy(details),
                    )
                )
    result.total_records = operation_index
    return result


def _load_document(content: str) -> dict[str, object]:
    try:
        loaded = json.loads(content)
    except json.JSONDecodeError:
        try:
            loaded = yaml.safe_load(content)
        except yaml.YAMLError as error:
            raise OpenApiParseError("OpenAPI document is not valid JSON or safe YAML") from error
    if not isinstance(loaded, dict):
        raise OpenApiParseError("OpenAPI document must be an object")
    return loaded


def _resolve(
    value: object,
    document: dict[str, object],
    warnings: list[str],
    context: str,
    seen: frozenset[str] = frozenset(),
) -> object:
    if not isinstance(value, dict) or "$ref" not in value:
        return value
    reference = value.get("$ref")
    if not isinstance(reference, str):
        warnings.append(f"{context}: malformed reference was ignored")
        return value
    if not reference.startswith("#/"):
        warnings.append(f"{context}: external reference is unsupported and was not fetched")
        return {"$ref": reference, "unresolved": True}
    if reference in seen:
        warnings.append(f"{context}: recursive internal reference was not expanded")
        return {"$ref": reference, "unresolved": True}
    current: object = document
    try:
        for part in reference[2:].split("/"):
            key = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, dict):
                raise KeyError(key)
            current = current[key]
    except KeyError:
        warnings.append(f"{context}: unresolved internal reference {reference}")
        return {"$ref": reference, "unresolved": True}
    return _resolve(current, document, warnings, context, seen | {reference})


def _servers(value: object, context: str, warnings: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"{context}: malformed servers list was ignored")
        return []
    servers: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            warnings.append(f"{context}: malformed server {index} was ignored")
            continue
        server_url = _expand_server(item["url"], item.get("variables"))
        parsed = urlsplit(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            warnings.append(f"{context}: invalid server URL was ignored")
            continue
        try:
            port = parsed.port
        except ValueError:
            warnings.append(f"{context}: invalid server port was ignored")
            continue
        del port
        servers.append(server_url.rstrip("/"))
    return servers


def _expand_server(url: str, variables: object) -> str:
    if not isinstance(variables, dict):
        return url
    expanded = url
    for name, definition in variables.items():
        if isinstance(name, str) and isinstance(definition, dict):
            default = definition.get("default")
            if isinstance(default, (str, int, float)):
                expanded = expanded.replace("{" + name + "}", str(default))
    return expanded


def _security_schemes(
    document: dict[str, object], warnings: list[str]
) -> dict[str, dict[str, object]]:
    components = document.get("components")
    if not isinstance(components, dict):
        return {}
    raw_schemes = components.get("securitySchemes")
    if not isinstance(raw_schemes, dict):
        return {}
    schemes: dict[str, dict[str, object]] = {}
    for name, raw_scheme in raw_schemes.items():
        scheme = _resolve(raw_scheme, document, warnings, f"security scheme {name}")
        if not isinstance(name, str) or not isinstance(scheme, dict):
            continue
        scheme_type = scheme.get("type")
        if scheme_type == "http":
            kind = str(scheme.get("scheme", "HTTP")).title()
        elif scheme_type == "apiKey":
            kind = "Cookie" if scheme.get("in") == "cookie" else "API key"
        elif scheme_type == "oauth2":
            kind = "OAuth2"
        elif scheme_type == "openIdConnect":
            kind = "OpenID Connect"
        else:
            kind = str(scheme_type or "Unknown")
        schemes[name] = {
            "name": name,
            "kind": kind,
            "location": scheme.get("in"),
            "parameter_name": scheme.get("name"),
        }
    return schemes


def _operation_details(
    document: dict[str, object],
    path_item: dict[str, object],
    operation: dict[str, object],
    schemes: dict[str, dict[str, object]],
    method: str,
    path: str,
    warnings: list[str],
) -> dict[str, object]:
    context = f"{method} {path}"
    parameters: list[dict[str, object]] = []
    for raw_parameter in [
        *(_as_list(path_item.get("parameters"))),
        *(_as_list(operation.get("parameters"))),
    ]:
        parameter = _resolve(raw_parameter, document, warnings, context)
        if not isinstance(parameter, dict):
            continue
        parameters.append(
            {
                "name": parameter.get("name"),
                "in": parameter.get("in"),
                "required": bool(parameter.get("required", False)),
                "schema": _resolve(parameter.get("schema"), document, warnings, context),
            }
        )
    request_body = _resolve(operation.get("requestBody"), document, warnings, context)
    request_content: list[str] = []
    request_schema: object = None
    if isinstance(request_body, dict) and isinstance(request_body.get("content"), dict):
        request_content = list(request_body["content"].keys())
        if request_content:
            media = request_body["content"].get(request_content[0])
            if isinstance(media, dict):
                request_schema = _resolve(media.get("schema"), document, warnings, context)
    responses: dict[str, object] = {}
    raw_responses = operation.get("responses")
    if isinstance(raw_responses, dict):
        for code, raw_response in raw_responses.items():
            response = _resolve(raw_response, document, warnings, context)
            content_types = []
            if isinstance(response, dict) and isinstance(response.get("content"), dict):
                content_types = list(response["content"].keys())
            responses[str(code)] = {"content_types": content_types}
    security = operation.get("security", document.get("security", []))
    auth: list[dict[str, object]] = []
    for requirement in _as_list(security):
        if isinstance(requirement, dict):
            for name in requirement:
                auth.append(schemes.get(name, {"name": name, "kind": "Unknown"}))
    return {
        "operation_id": operation.get("operationId"),
        "summary": operation.get("summary"),
        "tags": operation.get("tags") if isinstance(operation.get("tags"), list) else [],
        "parameters": parameters,
        "request_content_types": request_content,
        "request_schema": request_schema,
        "responses": responses,
        "security": auth,
    }


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
