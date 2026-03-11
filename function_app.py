import azure.functions as func
import json
import logging
from typing import Any

# Import services
from services import DatabricksService

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# Initialize services
databricks_service = DatabricksService()


def get_authenticated_user(req: func.HttpRequest) -> str:
    """Extract authenticated user from Azure Easy Auth headers"""
    return req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "unknown")


def create_response(body: Any, status_code: int = 200) -> func.HttpResponse:
    """Create HTTP response with JSON body"""
    return func.HttpResponse(
        body=json.dumps(body, default=str),
        status_code=status_code,
        mimetype="application/json"
    )


# ============================================================================
# NPT TRACKER ENDPOINTS (READ-ONLY - Data from Discord NPT Tracker)
# ============================================================================

NPT_TABLE = "paloma.discord.npt_tracker"

@app.route(route="npt", methods=["GET"])
def get_all_npt(req: func.HttpRequest) -> func.HttpResponse:
    """Get all NPT Tracker records"""
    try:
        records = databricks_service.get_all_records_from_table(NPT_TABLE, order_by="event_date_format_date DESC")
        return create_response({"data": records, "count": len(records)})
    except Exception as e:
        return create_response({"error": str(e)}, 500)


@app.route(route="npt/{id}", methods=["GET"])
def get_npt_by_id(req: func.HttpRequest) -> func.HttpResponse:
    """Get a single NPT Tracker record by message_id"""
    try:
        record_id = req.route_params.get("id")
        record = databricks_service.get_record_from_table(NPT_TABLE, record_id, id_column="message_id")

        if not record:
            return create_response({"error": "Record not found"}, 404)

        return create_response(record)
    except Exception as e:
        return create_response({"error": str(e)}, 500)


@app.route(route="npt/customer/{customer}", methods=["GET"])
def get_npt_by_customer(req: func.HttpRequest) -> func.HttpResponse:
    """Get all NPT records for a specific customer"""
    try:
        customer = req.route_params.get("customer")
        escaped_customer = customer.replace("'", "''")
        query = f"""
            SELECT * FROM {NPT_TABLE}
            WHERE UPPER(customer_name) = UPPER('{escaped_customer}')
            ORDER BY event_date_format_date DESC
        """
        records = databricks_service.execute_query(query)
        return create_response({"data": records, "count": len(records), "customer_name": customer})
    except Exception as e:
        return create_response({"error": str(e)}, 500)


@app.route(route="npt/asset-type/{asset_type}", methods=["GET"])
def get_npt_by_asset_type(req: func.HttpRequest) -> func.HttpResponse:
    """Get all NPT records for a specific asset type"""
    try:
        asset_type = req.route_params.get("asset_type")
        escaped_asset = asset_type.replace("'", "''")
        query = f"""
            SELECT * FROM {NPT_TABLE}
            WHERE UPPER(asset_type) = UPPER('{escaped_asset}')
            ORDER BY event_date_format_date DESC
        """
        records = databricks_service.execute_query(query)
        return create_response({"data": records, "count": len(records), "asset_type": asset_type})
    except Exception as e:
        return create_response({"error": str(e)}, 500)


@app.route(route="npt/year/{year}", methods=["GET"])
def get_npt_by_year(req: func.HttpRequest) -> func.HttpResponse:
    """Get all NPT records for a specific year"""
    try:
        year = req.route_params.get("year")
        query = f"""
            SELECT * FROM {NPT_TABLE}
            WHERE YEAR(event_date_format_date) = {int(year)}
            ORDER BY event_date_format_date DESC
        """
        records = databricks_service.execute_query(query)
        return create_response({"data": records, "count": len(records), "year": year})
    except Exception as e:
        return create_response({"error": str(e)}, 500)


@app.route(route="npt/year/{year}/month/{month}", methods=["GET"])
def get_npt_by_year_month(req: func.HttpRequest) -> func.HttpResponse:
    """Get all NPT records for a specific year and month"""
    try:
        year = req.route_params.get("year")
        month = req.route_params.get("month")
        query = f"""
            SELECT * FROM {NPT_TABLE}
            WHERE YEAR(event_date_format_date) = {int(year)}
              AND MONTH(event_date_format_date) = {int(month)}
            ORDER BY event_date_format_date DESC
        """
        records = databricks_service.execute_query(query)
        return create_response({"data": records, "count": len(records), "year": year, "month": month})
    except Exception as e:
        return create_response({"error": str(e)}, 500)


# ============================================================================
# NPT CREATE ENDPOINT
# ============================================================================

import hashlib
from datetime import datetime


def generate_npt_id() -> str:
    """Generate a unique NPT ID based on current timestamp"""
    now = datetime.utcnow()
    raw = f"NPT-{now.isoformat()}-{id(now)}"
    hash_hex = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"NPT-{hash_hex.upper()}"


@app.route(route="npt", methods=["POST"])
def create_npt(req: func.HttpRequest) -> func.HttpResponse:
    """Create a new NPT record"""
    try:
        body = req.get_json()

        # Validate required fields
        required_fields = ["customer_name", "well_name_and_number", "event_type", "asset_type"]
        missing = [f for f in required_fields if not body.get(f)]
        if missing:
            return create_response({"error": f"Missing required fields: {', '.join(missing)}"}, 400)

        # Get the authenticated user from token
        created_by = get_authenticated_user(req)

        # Generate unique NPT ID
        npt_id = generate_npt_id()
        now = datetime.utcnow().isoformat()

        # Build record data
        record = {
            "npt_id": npt_id,
            "customer_name": body.get("customer_name"),
            "well_name_and_number": body.get("well_name_and_number"),
            "well_number": body.get("well_number", ""),
            "event_type": body.get("event_type"),
            "asset_type": body.get("asset_type"),
            "asset_sub_type": body.get("asset_sub_type", ""),
            "npt_time_minutes": body.get("npt_time_minutes", 0),
            "reason": body.get("reason", ""),
            "solution": body.get("solution", ""),
            "technician_name": body.get("technician_name", ""),
            "status": body.get("status", "Open"),
            "created_by": created_by,
            "created_at": now,
            "event_date_format_date": body.get("event_date_format_date", now),
        }

        # Build INSERT query
        columns = list(record.keys())
        def format_value(v):
            if v is None:
                return "NULL"
            elif isinstance(v, (int, float)):
                return str(v)
            else:
                escaped = str(v).replace("'", "''")
                return f"'{escaped}'"

        values = [format_value(record[col]) for col in columns]

        insert_sql = f"""
            INSERT INTO {NPT_TABLE} ({', '.join(columns)})
            VALUES ({', '.join(values)})
        """

        with databricks_service._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(insert_sql)

        logging.info(f"NPT record created: {npt_id} by {created_by}")

        return create_response({
            "success": True,
            "npt_id": npt_id,
            "created_by": created_by,
            "created_at": now
        }, 201)

    except ValueError as e:
        return create_response({"error": f"Invalid request body: {str(e)}"}, 400)
    except Exception as e:
        logging.error(f"Error creating NPT record: {str(e)}")
        return create_response({"error": str(e)}, 500)


# ============================================================================
# SWAGGER / OPENAPI ENDPOINT
# ============================================================================

@app.route(route="swagger.json", methods=["GET"])
def get_swagger(req: func.HttpRequest) -> func.HttpResponse:
    """Get OpenAPI/Swagger specification"""
    swagger_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "PAC API",
            "description": "API del equipo de ingenieria para servir y gestionar datos operacionales.",
            "version": "2.0.0",
            "contact": {
                "name": "Paloma Pressure Control"
            }
        },
        "servers": [
            {
                "url": "/api",
                "description": "API Server"
            }
        ],
        "tags": [
            {"name": "NPT Tracker", "description": "Non-Productive Time Tracker"}
        ],
        "paths": {
            "/npt": {
                "get": {
                    "tags": ["NPT Tracker"],
                    "summary": "Get all NPT records",
                    "description": "Returns all Non-Productive Time records ordered by event_date_format_date DESC",
                    "responses": {"200": {"description": "List of NPT records"}}
                },
                "post": {
                    "tags": ["NPT Tracker"],
                    "summary": "Create a new NPT record",
                    "description": "Creates a new NPT record with a unique auto-generated npt_id (hash)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["customer_name", "well_name_and_number", "event_type", "asset_type"],
                                    "properties": {
                                        "customer_name": {"type": "string"},
                                        "well_name_and_number": {"type": "string"},
                                        "well_number": {"type": "string"},
                                        "event_type": {"type": "string"},
                                        "asset_type": {"type": "string"},
                                        "asset_sub_type": {"type": "string"},
                                        "npt_time_minutes": {"type": "number"},
                                        "reason": {"type": "string"},
                                        "solution": {"type": "string"},
                                        "technician_name": {"type": "string"},
                                        "status": {"type": "string", "enum": ["Open", "Closed"], "default": "Open"},
                                        "event_date_format_date": {"type": "string", "description": "Event date (ISO format, defaults to now)"}
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {"description": "NPT record created successfully with npt_id"},
                        "400": {"description": "Missing required fields or invalid body"}
                    }
                }
            },
            "/npt/{id}": {
                "get": {
                    "tags": ["NPT Tracker"],
                    "summary": "Get NPT record by message_id",
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "message_id"}],
                    "responses": {"200": {"description": "NPT record found"}, "404": {"description": "Record not found"}}
                }
            },
            "/npt/customer/{customer}": {
                "get": {
                    "tags": ["NPT Tracker"],
                    "summary": "Get all NPT records for a specific customer",
                    "parameters": [{"name": "customer", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Customer name"}],
                    "responses": {"200": {"description": "List of NPT records for the customer"}}
                }
            },
            "/npt/asset-type/{asset_type}": {
                "get": {
                    "tags": ["NPT Tracker"],
                    "summary": "Get all NPT records for a specific asset type",
                    "parameters": [{"name": "asset_type", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Asset type name"}],
                    "responses": {"200": {"description": "List of NPT records for the asset type"}}
                }
            },
            "/npt/year/{year}": {
                "get": {
                    "tags": ["NPT Tracker"],
                    "summary": "Get all NPT records for a specific year",
                    "parameters": [{"name": "year", "in": "path", "required": True, "schema": {"type": "integer"}, "description": "Year (e.g. 2025, 2026)"}],
                    "responses": {"200": {"description": "List of NPT records for the year"}}
                }
            },
            "/npt/year/{year}/month/{month}": {
                "get": {
                    "tags": ["NPT Tracker"],
                    "summary": "Get all NPT records for a specific year and month",
                    "parameters": [
                        {"name": "year", "in": "path", "required": True, "schema": {"type": "integer"}, "description": "Year (e.g. 2025)"},
                        {"name": "month", "in": "path", "required": True, "schema": {"type": "integer"}, "description": "Month (1-12)"}
                    ],
                    "responses": {"200": {"description": "List of NPT records for the year and month"}}
                }
            }
        },
        "components": {
            "schemas": {},
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Microsoft Entra ID (Azure AD) Bearer token"
                }
            }
        },
        "security": [{"BearerAuth": []}]
    }
    return create_response(swagger_spec)


@app.route(route="", methods=["GET"])
def api_root(req: func.HttpRequest) -> func.HttpResponse:
    """API root - returns available endpoints"""
    return create_response({
        "name": "PAC API",
        "version": "2.0.0",
        "endpoints": {
            "swagger": "/api/swagger.json",
            "docs": "/api/docs",
            "npt": {
                "all_records": "/api/npt",
                "create": "/api/npt (POST)",
                "by_id": "/api/npt/{id}",
                "by_customer": "/api/npt/customer/{customer}",
                "by_asset_type": "/api/npt/asset-type/{asset_type}",
                "by_year": "/api/npt/year/{year}",
                "by_year_month": "/api/npt/year/{year}/month/{month}"
            }
        }
    })




@app.route(route="docs", methods=["GET"])
def swagger_ui(req: func.HttpRequest) -> func.HttpResponse:
    """Swagger UI - Interactive API documentation"""
    import base64
    import json as json_module

    # Try to get the display name from X-MS-CLIENT-PRINCIPAL (contains full user info)
    user_name = "Guest"
    principal_header = req.headers.get("X-MS-CLIENT-PRINCIPAL", "")

    if principal_header:
        try:
            # Decode the base64 encoded principal
            decoded = base64.b64decode(principal_header).decode('utf-8')
            principal_data = json_module.loads(decoded)

            # Look for name in claims
            claims = principal_data.get("claims", [])
            for claim in claims:
                claim_type = claim.get("typ", "")
                # Look for name claim (could be "name", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name", etc.)
                if claim_type == "name" or "name" in claim_type.lower():
                    user_name = claim.get("val", "")
                    if user_name and "@" not in user_name:  # Found actual name, not email
                        break

            # If still no name found, try preferred_username or email
            if user_name == "Guest" or "@" in user_name:
                for claim in claims:
                    claim_type = claim.get("typ", "")
                    if "givenname" in claim_type.lower():
                        given_name = claim.get("val", "")
                        if given_name:
                            user_name = given_name
                            break
        except Exception:
            pass

    # Fallback to X-MS-CLIENT-PRINCIPAL-NAME (usually email)
    if user_name == "Guest":
        user_name = req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "")
        if user_name and "@" in user_name:
            # Extract first part of email as name
            user_name = user_name.split("@")[0].replace(".", " ").title()

    if not user_name:
        user_name = "Guest"

    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PAC API - Paloma Analytics Center</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css">
    <style>
        :root {
            --primary-color: #3b82f6;
            --primary-hover: #2563eb;
            --success-color: #22c55e;
            --warning-color: #f59e0b;
            --danger-color: #ef4444;
            --bg-white: #ffffff;
            --bg-gray: #f8fafc;
            --bg-light: #f1f5f9;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;
            --border-color: #e2e8f0;
            --border-light: #f1f5f9;
        }
        html { box-sizing: border-box; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin: 0; background: var(--bg-gray); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }

        /* Clean white theme for Swagger UI */
        .swagger-ui { background: var(--bg-gray); }
        .swagger-ui .topbar { display: none; }
        .swagger-ui .info .title { color: var(--text-primary); font-weight: 600; }
        .swagger-ui .info { margin: 30px 0; }
        .swagger-ui .info .title small { background: var(--primary-color); color: white; padding: 4px 8px; border-radius: 4px; }
        .swagger-ui .info p, .swagger-ui .info li { color: var(--text-secondary); }
        .swagger-ui .info a { color: var(--primary-color); }
        .swagger-ui .scheme-container { background: var(--bg-white); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 20px; border-radius: 8px; margin-bottom: 20px; }

        /* Tags */
        .swagger-ui .opblock-tag {
            color: var(--text-primary);
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
            padding: 15px 0;
        }
        .swagger-ui .opblock-tag:hover { background: var(--bg-light); }
        .swagger-ui .opblock-tag small { color: var(--text-secondary); }

        /* Operation blocks */
        .swagger-ui .opblock {
            background: var(--bg-white);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }
        .swagger-ui .opblock .opblock-summary { border-radius: 8px; }
        .swagger-ui .opblock .opblock-summary-path { color: var(--text-primary); }
        .swagger-ui .opblock .opblock-summary-description { color: var(--text-secondary); }

        /* HTTP Methods */
        .swagger-ui .opblock.opblock-get { background: var(--bg-white); border-left: 4px solid #3b82f6; }
        .swagger-ui .opblock.opblock-get .opblock-summary-method { background: #3b82f6; }
        .swagger-ui .opblock.opblock-post { background: var(--bg-white); border-left: 4px solid #22c55e; }
        .swagger-ui .opblock.opblock-post .opblock-summary-method { background: #22c55e; }
        .swagger-ui .opblock.opblock-put { background: var(--bg-white); border-left: 4px solid #f59e0b; }
        .swagger-ui .opblock.opblock-put .opblock-summary-method { background: #f59e0b; }
        .swagger-ui .opblock.opblock-delete { background: var(--bg-white); border-left: 4px solid #ef4444; }
        .swagger-ui .opblock.opblock-delete .opblock-summary-method { background: #ef4444; }

        .swagger-ui .opblock-body { background: var(--bg-gray); }
        .swagger-ui .opblock-section-header { background: var(--bg-light); border-radius: 4px; }
        .swagger-ui .opblock-section-header h4 { color: var(--text-primary); }
        .swagger-ui .opblock-description-wrapper p { color: var(--text-secondary); }

        /* Tables */
        .swagger-ui table thead tr th { color: var(--text-primary); border-bottom: 2px solid var(--border-color); }
        .swagger-ui table tbody tr td { color: var(--text-secondary); border-bottom: 1px solid var(--border-light); }
        .swagger-ui .parameter__name { color: var(--text-primary); }
        .swagger-ui .parameter__name.required:after { color: var(--danger-color); }
        .swagger-ui .parameter__type { color: var(--primary-color); }
        .swagger-ui .parameter__in { color: var(--text-muted); }

        /* Responses */
        .swagger-ui .response-col_status { color: var(--success-color); font-weight: 600; }
        .swagger-ui .response-col_description { color: var(--text-secondary); }
        .swagger-ui .responses-inner { background: var(--bg-gray); }
        .swagger-ui .response { background: var(--bg-white); border-radius: 4px; }

        /* Models */
        .swagger-ui .model-title { color: var(--text-primary); }
        .swagger-ui .model { color: var(--text-secondary); }
        .swagger-ui .model-box { background: var(--bg-white); border-radius: 4px; }
        .swagger-ui section.models { border: 1px solid var(--border-color); border-radius: 8px; background: var(--bg-white); }
        .swagger-ui section.models h4 { color: var(--text-primary); }
        .swagger-ui section.models.is-open h4 { border-bottom: 1px solid var(--border-color); }

        /* Buttons */
        .swagger-ui .btn {
            background: var(--primary-color);
            color: white;
            border: none;
            border-radius: 6px;
            font-weight: 500;
        }
        .swagger-ui .btn:hover { background: var(--primary-hover); }
        .swagger-ui .btn.execute { background: var(--success-color); color: white; font-weight: 600; }
        .swagger-ui .btn.execute:hover { background: #16a34a; }
        .swagger-ui .btn.cancel { background: var(--text-muted); }

        /* Form elements */
        .swagger-ui select {
            background: var(--bg-white);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
        }
        .swagger-ui input[type=text], .swagger-ui input[type=password], .swagger-ui input[type=search] {
            background: var(--bg-white);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
        }
        .swagger-ui textarea {
            background: var(--bg-white);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
        }

        /* Filter */
        .swagger-ui .filter-container { background: var(--bg-white); padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .swagger-ui .filter input { background: var(--bg-white); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 6px; }

        /* Wrapper */
        .swagger-ui .wrapper { background: var(--bg-gray); padding: 0 20px; max-width: 1400px; }
        .swagger-ui .information-container { background: var(--bg-gray); }

        /* Custom header - Clean white theme */
        .custom-header {
            background: var(--bg-white);
            color: var(--text-primary);
            padding: 20px 30px;
            border-bottom: 1px solid var(--border-color);
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            position: relative;
            z-index: 1000;
        }
        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .custom-header h1 {
            margin: 0;
            font-size: 22px;
            font-weight: 600;
            color: var(--text-primary);
        }
        .custom-header .version {
            background: var(--bg-light);
            color: var(--text-secondary);
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
        }
        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .header-logo {
            display: flex;
            align-items: center;
            gap: 8px;
            background: #104432;
            padding: 8px 15px;
            border-radius: 8px;
        }
        .header-logo .logo-text {
            font-size: 20px;
            font-weight: 700;
            color: #104432;
            letter-spacing: 1px;
        }
        .header-logo .logo-subtitle {
            font-size: 10px;
            color: #476751;
            letter-spacing: 0.5px;
            margin-top: -2px;
        }
        .header-logo .logo-img {
            height: 50px;
            width: auto;
        }
        .header-logo svg {
            height: 50px;
            width: auto;
        }
        .header-flags {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 28px;
            padding-left: 15px;
            border-left: 2px solid var(--border-color);
        }
        .user-banner {
            background: linear-gradient(135deg, #104432 0%, #476751 100%);
            color: white;
            padding: 10px 30px;
            text-align: center;
            font-size: 14px;
        }
        .user-banner strong {
            color: #c1d82f;
        }
    </style>
</head>
<body>
    <div class="user-banner">
        <span>Hi <strong>USER_NAME_PLACEHOLDER</strong>, hero of the technology team</span>
    </div>
    <div class="custom-header">
        <div class="header-content">
            <div class="header-left">
                <div class="header-logo">
                    <img src="https://cdn.prod.website-files.com/689cf18056299d8474c31f01/689cf18056299d8474c3206b_Paloma%20Logo%203.0.svg" alt="Paloma Pressure Control" class="logo-img">
                </div>
                <div class="header-flags">
                    <span title="USA">&#127482;&#127480;</span>
                </div>
            </div>
            <span class="version">v2.0.0</span>
        </div>
    </div>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {
            const ui = SwaggerUIBundle({
                url: "/api/swagger.json",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout",
                defaultModelsExpandDepth: 1,
                defaultModelExpandDepth: 1,
                docExpansion: "list",
                filter: true,
                showExtensions: true,
                showCommonExtensions: true
            });
            window.ui = ui;
        };
    </script>
</body>
</html>'''
    # Replace placeholder with actual user name
    html = html.replace("USER_NAME_PLACEHOLDER", user_name)

    return func.HttpResponse(
        body=html,
        status_code=200,
        mimetype="text/html"
    )
