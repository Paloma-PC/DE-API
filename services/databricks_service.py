import os
from typing import Dict, Any, List, Optional
from databricks import sql


class DatabricksService:
    """Service for storing and retrieving data from Databricks"""

    def __init__(self):
        self.host = os.environ.get("DATABRICKS_HOST")
        self.token = os.environ.get("DATABRICKS_TOKEN")
        self.catalog = os.environ.get("DATABRICKS_CATALOG", "paloma")
        self.schema = os.environ.get("DATABRICKS_SCHEMA", "canada")
        self.http_path = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/2b9a6633836c53b8")

    def _get_connection(self):
        """Get Databricks SQL connection"""
        if not self.host or not self.token:
            raise ValueError("Databricks host and token must be configured")

        return sql.connect(
            server_hostname=self.host.replace("https://", ""),
            http_path=self.http_path,
            access_token=self.token
        )

    def _get_table_name(self, form_type: str) -> str:
        """Get full table name for form type"""
        return f"{self.catalog}.{self.schema}.{form_type}"

    def _ensure_table_exists(self, form_type: str, columns: Dict[str, str]):
        """Create table if it doesn't exist, and add missing columns to existing tables"""
        table_name = self._get_table_name(form_type)

        column_defs = []
        for col_name, col_type in columns.items():
            column_defs.append(f"{col_name} {col_type}")

        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {', '.join(column_defs)}
        )
        """

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(create_sql)

                    # Check existing columns and add missing ones
                    cursor.execute(f"DESCRIBE TABLE {table_name}")
                    existing_cols = {row[0].lower() for row in cursor.fetchall()}

                    for col_name, col_type in columns.items():
                        if col_name.lower() not in existing_cols:
                            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                            print(f"Adding missing column: {col_name} to {table_name}")
                            cursor.execute(alter_sql)

        except Exception as e:
            print(f"Error ensuring table exists: {str(e)}")

    # Table schemas for each form type
    TABLE_SCHEMAS = {
        "mfv_build_tolerance": {
            "id": "STRING",
            "name": "STRING",
            "ppc": "STRING",
            "shop_origin": "STRING",
            "valve_size": "STRING",
            "body_style": "STRING",
            "seal_configuration": "STRING",
            "gate_guides_installed": "STRING",
            "step_size": "STRING",
            "seat_pocket_to_seat_pocket": "STRING",
            "a_side_seat_thickness": "STRING",
            "b_side_seat_thickness": "STRING",
            "gate_thickness": "STRING",
            "created_by": "STRING",
            "updated_by": "STRING",
            "created_at": "STRING",
            "updated_at": "STRING",
            "discord_message_id": "STRING"
        },
        "mfv_test_report": {
            "id": "STRING",
            "name": "STRING",
            "ppc": "STRING",
            "valve_size": "STRING",
            "shop_origin": "STRING",
            "body_style": "STRING",
            "is_retest": "STRING",
            "prior_job_code": "STRING",
            "shell_test": "STRING",
            "bore_test": "STRING",
            "gate_a_side": "STRING",
            "gate_b_side": "STRING",
            "body_pressure_a_side": "STRING",
            "body_pressure_b_side": "STRING",
            "valve_qualification": "STRING",
            "created_by": "STRING",
            "updated_by": "STRING",
            "created_at": "STRING",
            "updated_at": "STRING",
            "discord_message_id": "STRING"
        },
        "oem_valve_completion": {
            "id": "STRING",
            "ppc": "STRING",
            "valve_size_operator": "STRING",
            "shop_origin": "STRING",
            "created_by": "STRING",
            "updated_by": "STRING",
            "created_at": "STRING",
            "updated_at": "STRING",
            "discord_message_id": "STRING"
        },
        "service_equipment_maintenance": {
            "id": "STRING",
            "category": "STRING",
            "unit_number": "STRING",
            "issue_location": "STRING",
            "description": "STRING",
            "created_by": "STRING",
            "updated_by": "STRING",
            "created_at": "STRING",
            "updated_at": "STRING",
            "discord_message_id": "STRING"
        },
        "slv_ppc": {
            "id": "STRING",
            "customer_lsd": "STRING",
            "slv_entries": "STRING",
            "created_by": "STRING",
            "updated_by": "STRING",
            "created_at": "STRING",
            "updated_at": "STRING",
            "discord_message_id": "STRING"
        }
    }

    def insert_record(self, form_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a new record into Databricks

        Args:
            form_type: Type of form
            data: Record data

        Returns:
            Dict with 'success' (bool) and 'error' (str) if failed
        """
        try:
            # Ensure table exists
            if form_type in self.TABLE_SCHEMAS:
                self._ensure_table_exists(form_type, self.TABLE_SCHEMAS[form_type])

            table_name = self._get_table_name(form_type)

            # Handle special case for slv_entries (convert list to JSON string)
            if "slv_entries" in data and isinstance(data["slv_entries"], list):
                import json
                data = data.copy()
                data["slv_entries"] = json.dumps(data["slv_entries"])

            columns = list(data.keys())

            # Format values for SQL (escape strings properly)
            def format_value(v):
                if v is None:
                    return "NULL"
                elif isinstance(v, str):
                    # Escape single quotes by doubling them
                    escaped = str(v).replace("'", "''")
                    return f"'{escaped}'"
                else:
                    return f"'{v}'"

            formatted_values = [format_value(data[col]) for col in columns]

            insert_sql = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({', '.join(formatted_values)})
            """

            print(f"Executing Databricks INSERT: {insert_sql[:200]}...")

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_sql)

            print(f"Databricks INSERT successful for {form_type}")
            return {"success": True}

        except Exception as e:
            error_msg = f"Error inserting record into Databricks: {str(e)}"
            print(error_msg)
            return {"success": False, "error": error_msg}

    def update_record(self, form_type: str, record_id: str, data: Dict[str, Any]) -> bool:
        """
        Update an existing record in Databricks

        Args:
            form_type: Type of form
            record_id: ID of the record to update
            data: Updated data

        Returns:
            True if successful, False otherwise
        """
        try:
            table_name = self._get_table_name(form_type)

            # Handle special case for slv_entries
            if "slv_entries" in data and isinstance(data["slv_entries"], list):
                import json
                data = data.copy()
                data["slv_entries"] = json.dumps(data["slv_entries"])

            # Format value for SQL
            def format_value(v):
                if v is None:
                    return "NULL"
                elif isinstance(v, str):
                    escaped = str(v).replace("'", "''")
                    return f"'{escaped}'"
                else:
                    return f"'{v}'"

            set_clauses = []
            for col, val in data.items():
                if col != "id":
                    set_clauses.append(f"{col} = {format_value(val)}")

            escaped_id = record_id.replace("'", "''")

            update_sql = f"""
            UPDATE {table_name}
            SET {', '.join(set_clauses)}
            WHERE id = '{escaped_id}'
            """

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(update_sql)

            return True

        except Exception as e:
            print(f"Error updating record in Databricks: {str(e)}")
            return False

    def delete_record(self, form_type: str, record_id: str) -> bool:
        """
        Delete a record from Databricks

        Args:
            form_type: Type of form
            record_id: ID of the record to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            table_name = self._get_table_name(form_type)

            escaped_id = record_id.replace("'", "''")
            delete_sql = f"DELETE FROM {table_name} WHERE id = '{escaped_id}'"

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(delete_sql)

            return True

        except Exception as e:
            print(f"Error deleting record from Databricks: {str(e)}")
            return False

    def get_record(self, form_type: str, record_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single record by ID

        Args:
            form_type: Type of form
            record_id: ID of the record

        Returns:
            Record data or None if not found
        """
        try:
            table_name = self._get_table_name(form_type)

            escaped_id = record_id.replace("'", "''")
            select_sql = f"SELECT * FROM {table_name} WHERE id = '{escaped_id}'"

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_sql)
                    row = cursor.fetchone()

                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        record = dict(zip(columns, row))

                        # Convert slv_entries back to list
                        if "slv_entries" in record and isinstance(record["slv_entries"], str):
                            import json
                            record["slv_entries"] = json.loads(record["slv_entries"])

                        return record

            return None

        except Exception as e:
            print(f"Error getting record from Databricks: {str(e)}")
            return None

    def get_all_records(self, form_type: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all records for a form type

        Args:
            form_type: Type of form
            limit: Maximum number of records to return
            offset: Number of records to skip

        Returns:
            List of records
        """
        table_name = self._get_table_name(form_type)

        select_sql = f"SELECT * FROM {table_name} ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"

        records = []

        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_sql)
                columns = [desc[0] for desc in cursor.description]

                for row in cursor.fetchall():
                    record = dict(zip(columns, row))

                    # Convert slv_entries back to list
                    if "slv_entries" in record and isinstance(record["slv_entries"], str):
                        import json
                        record["slv_entries"] = json.loads(record["slv_entries"])

                    records.append(record)

        return records

    def get_all_records_from_table(self, full_table_name: str, order_by: str = "event_date DESC", limit: int = None) -> List[Dict[str, Any]]:
        """
        Get all records from a specific table (for external tables like discord.npt_tracker)

        Args:
            full_table_name: Full table name (e.g., 'paloma.discord.npt_tracker')
            order_by: Column and direction to order by (default: event_date DESC)
            limit: Maximum number of records to return (None = no limit)

        Returns:
            List of records
        """
        select_sql = f"SELECT * FROM {full_table_name} ORDER BY {order_by}"
        if limit:
            select_sql += f" LIMIT {limit}"

        records = []

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_sql)
                    columns = [desc[0] for desc in cursor.description]

                    for row in cursor.fetchall():
                        record = dict(zip(columns, row))
                        records.append(record)
        except Exception as e:
            print(f"Error getting records from {full_table_name}: {str(e)}")

        return records

    def get_record_from_table(self, full_table_name: str, record_id: str, id_column: str = "message_id") -> Optional[Dict[str, Any]]:
        """
        Get a single record from a specific table by ID

        Args:
            full_table_name: Full table name (e.g., 'paloma.discord.npt_tracker')
            record_id: ID of the record
            id_column: Name of the ID column (default: message_id)

        Returns:
            Record data or None if not found
        """
        try:
            escaped_id = record_id.replace("'", "''")
            select_sql = f"SELECT * FROM {full_table_name} WHERE {id_column} = '{escaped_id}'"

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_sql)
                    row = cursor.fetchone()

                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        return dict(zip(columns, row))

            return None

        except Exception as e:
            print(f"Error getting record from {full_table_name}: {str(e)}")
            return None

    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Execute a raw SQL query (SELECT only for safety)

        Args:
            query: SQL query to execute (must be SELECT)

        Returns:
            List of records
        """
        # Safety check - only allow SELECT queries
        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")

        records = []

        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    columns = [desc[0] for desc in cursor.description]

                    for row in cursor.fetchall():
                        record = dict(zip(columns, row))
                        records.append(record)
        except Exception as e:
            print(f"Error executing query: {str(e)}")
            raise

        return records
