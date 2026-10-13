from typing import Dict, Any, Optional, Set
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent.schemas import ToolCallIntent, ToolExecutionResult
from app.services.doctor_service import search_doctors_tool, get_available_slots_tool
from app.services.appointment_service import book_appointment_tool


class RestrictedToolRouter:
    """
    Restricted tool router that securely exposes only allowlisted backend tools to the AI agent.
    The agent and model are strictly isolated from direct database/SQL access.
    All calls are validated against exact schemas before invocation.
    """

    ALLOWED_TOOLS: Set[str] = {
        "search_doctors",
        "get_available_slots",
        "book_appointment",
    }

    def execute_tool(self, db: Session, intent: ToolCallIntent) -> ToolExecutionResult:
        """
        Validates the tool name and arguments, executes the allowlisted tool against
        the verified backend service, and returns a structured ToolExecutionResult.
        """
        tool_name = intent.tool_name.strip()
        args = intent.arguments

        # 1. Enforce strict allowlist
        if tool_name not in self.ALLOWED_TOOLS:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=(
                    f"Access Denied: Tool '{tool_name}' is not permitted. "
                    f"Only allowlisted tools ({', '.join(sorted(self.ALLOWED_TOOLS))}) are accessible."
                ),
            )

        # 2. Dispatch with strict argument validation
        try:
            if tool_name == "search_doctors":
                return self._execute_search_doctors(db, args)
            elif tool_name == "get_available_slots":
                return self._execute_get_available_slots(db, args)
            elif tool_name == "book_appointment":
                return self._execute_book_appointment(db, args)
            else:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Unrecognized tool: '{tool_name}'",
                )
        except HTTPException as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"HTTP {exc.status_code}: {exc.detail}",
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Execution error in '{tool_name}': {str(exc)}",
            )

    def _execute_search_doctors(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        # Check for disallowed keys
        allowed_keys = {"specialty_or_department", "hospital_id"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="search_doctors",
                success=False,
                error=f"Invalid arguments for search_doctors: {sorted(list(disallowed))}",
            )

        specialty_or_dept = args.get("specialty_or_department")
        if specialty_or_dept is not None and not isinstance(specialty_or_dept, str):
            return ToolExecutionResult(
                tool_name="search_doctors",
                success=False,
                error="Argument 'specialty_or_department' must be a string.",
            )

        hospital_id = args.get("hospital_id")
        if hospital_id is not None and not isinstance(hospital_id, str):
            return ToolExecutionResult(
                tool_name="search_doctors",
                success=False,
                error="Argument 'hospital_id' must be a string.",
            )

        results = search_doctors_tool(
            db=db,
            specialty_or_department=specialty_or_dept,
            hospital_id=hospital_id,
        )
        return ToolExecutionResult(
            tool_name="search_doctors",
            success=True,
            data=results,
        )

    def _execute_get_available_slots(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        allowed_keys = {"doctor_id", "requested_date", "time_range"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="get_available_slots",
                success=False,
                error=f"Invalid arguments for get_available_slots: {sorted(list(disallowed))}",
            )

        doctor_id = args.get("doctor_id")
        if not doctor_id or not isinstance(doctor_id, str) or not doctor_id.strip():
            return ToolExecutionResult(
                tool_name="get_available_slots",
                success=False,
                error="Missing required argument 'doctor_id' (must be a non-empty string).",
            )

        requested_date = args.get("requested_date")
        if requested_date is not None and not isinstance(requested_date, str):
            return ToolExecutionResult(
                tool_name="get_available_slots",
                success=False,
                error="Argument 'requested_date' must be a string in YYYY-MM-DD format.",
            )

        time_range = args.get("time_range")
        if time_range is not None and not isinstance(time_range, str):
            return ToolExecutionResult(
                tool_name="get_available_slots",
                success=False,
                error="Argument 'time_range' must be a string.",
            )

        results = get_available_slots_tool(
            db=db,
            doctor_id=doctor_id.strip(),
            requested_date=requested_date,
            time_range=time_range,
        )
        return ToolExecutionResult(
            tool_name="get_available_slots",
            success=True,
            data=results,
        )

    def _execute_book_appointment(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        allowed_keys = {"patient_reference", "doctor_id", "selected_slot_id", "slot_id", "reason_category"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="book_appointment",
                success=False,
                error=f"Invalid arguments for book_appointment: {sorted(list(disallowed))}",
            )

        patient_ref = args.get("patient_reference")
        doctor_id = args.get("doctor_id")
        slot_id = args.get("selected_slot_id") or args.get("slot_id")
        reason = args.get("reason_category")

        # Validate non-empty required fields
        if not patient_ref or not isinstance(patient_ref, str) or not patient_ref.strip():
            return ToolExecutionResult(
                tool_name="book_appointment",
                success=False,
                error="Missing required argument 'patient_reference'.",
            )
        if not doctor_id or not isinstance(doctor_id, str) or not doctor_id.strip():
            return ToolExecutionResult(
                tool_name="book_appointment",
                success=False,
                error="Missing required argument 'doctor_id'.",
            )
        if not slot_id or not isinstance(slot_id, str) or not slot_id.strip():
            return ToolExecutionResult(
                tool_name="book_appointment",
                success=False,
                error="Missing required argument 'selected_slot_id'.",
            )
        if not reason or not isinstance(reason, str) or not reason.strip():
            return ToolExecutionResult(
                tool_name="book_appointment",
                success=False,
                error="Missing required argument 'reason_category'.",
            )

        result = book_appointment_tool(
            db=db,
            patient_reference=patient_ref.strip(),
            doctor_id=doctor_id.strip(),
            selected_slot_id=slot_id.strip(),
            reason_category=reason.strip(),
        )
        return ToolExecutionResult(
            tool_name="book_appointment",
            success=True,
            data=result,
        )
