from typing import Dict, Any, Optional, Set
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agent.schemas import ToolCallIntent, ToolExecutionResult
from app.services.doctor_service import search_doctors_tool, get_available_slots_tool, deduplicate_doctors
from app.services.appointment_service import book_appointment_tool
from app.services.lab_service import check_lab_report_status_tool
from app.services.insurance_service import search_hospital_insurance_tool
from app.services.patient_service import register_patient_tool, verify_patient_tool


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
        "check_lab_report_status",
        "search_hospital_insurance",
        "register_patient",
        "verify_patient",
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
            elif tool_name == "check_lab_report_status":
                return self._execute_check_lab_report_status(db, args)
            elif tool_name == "search_hospital_insurance":
                return self._execute_search_hospital_insurance(db, args)
            elif tool_name == "register_patient":
                return self._execute_register_patient(db, args)
            elif tool_name == "verify_patient":
                return self._execute_verify_patient(db, args)
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
            data=deduplicate_doctors(results),
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

    def _execute_check_lab_report_status(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        allowed_keys = {"verification_code", "session_key"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="check_lab_report_status",
                success=False,
                error=f"Invalid arguments for check_lab_report_status: {sorted(list(disallowed))}",
            )

        code = args.get("verification_code")
        if code is None or not isinstance(code, str) or not code.strip():
            return ToolExecutionResult(
                tool_name="check_lab_report_status",
                success=False,
                error="Missing required argument 'verification_code' (must be a 6-digit string).",
            )

        session_key = args.get("session_key")
        if session_key is not None and not isinstance(session_key, str):
            return ToolExecutionResult(
                tool_name="check_lab_report_status",
                success=False,
                error="Argument 'session_key' must be a string.",
            )

        result = check_lab_report_status_tool(
            db=db,
            verification_code=code.strip(),
            session_key=session_key,
        )
        return ToolExecutionResult(
            tool_name="check_lab_report_status",
            success=True,
            data=result,
        )

    def _execute_search_hospital_insurance(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        allowed_keys = {"provider_name", "plan_type", "service", "cashless", "plan_name", "query"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error=f"Invalid arguments for search_hospital_insurance: {sorted(list(disallowed))}",
            )

        provider_name = args.get("provider_name")
        if provider_name is not None and not isinstance(provider_name, str):
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error="Argument 'provider_name' must be a string.",
            )

        plan_type = args.get("plan_type")
        if plan_type is not None and not isinstance(plan_type, str):
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error="Argument 'plan_type' must be a string.",
            )

        service = args.get("service")
        if service is not None and not isinstance(service, str):
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error="Argument 'service' must be a string.",
            )

        cashless = args.get("cashless")
        if cashless is not None and not isinstance(cashless, bool):
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error="Argument 'cashless' must be a boolean.",
            )

        plan_name = args.get("plan_name")
        if plan_name is not None and not isinstance(plan_name, str):
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error="Argument 'plan_name' must be a string.",
            )

        query = args.get("query")
        if query is not None and not isinstance(query, str):
            return ToolExecutionResult(
                tool_name="search_hospital_insurance",
                success=False,
                error="Argument 'query' must be a string.",
            )

        result = search_hospital_insurance_tool(
            db=db,
            provider_name=provider_name,
            plan_type=plan_type,
            service=service,
            cashless=cashless,
            plan_name=plan_name,
            query=query,
        )
        return ToolExecutionResult(
            tool_name="search_hospital_insurance",
            success=True,
            data=result,
        )

    def _execute_register_patient(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        allowed_keys = {"full_name", "phone_number"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="register_patient",
                success=False,
                error=f"Invalid arguments for register_patient: {sorted(list(disallowed))}",
            )

        full_name = args.get("full_name")
        if not full_name or not isinstance(full_name, str):
            return ToolExecutionResult(
                tool_name="register_patient",
                success=False,
                error="Argument 'full_name' must be a non-empty string.",
            )

        phone_number = args.get("phone_number")
        if not phone_number or not isinstance(phone_number, str):
            return ToolExecutionResult(
                tool_name="register_patient",
                success=False,
                error="Argument 'phone_number' must be a valid phone number string.",
            )

        try:
            res = register_patient_tool(db=db, full_name=full_name, phone_number=phone_number)
            return ToolExecutionResult(
                tool_name="register_patient",
                success=True,
                data=res,
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name="register_patient",
                success=False,
                error=str(exc),
            )

    def _execute_verify_patient(self, db: Session, args: Dict[str, Any]) -> ToolExecutionResult:
        allowed_keys = {"patient_reference", "phone_number"}
        disallowed = set(args.keys()) - allowed_keys
        if disallowed:
            return ToolExecutionResult(
                tool_name="verify_patient",
                success=False,
                error=f"Invalid arguments for verify_patient: {sorted(list(disallowed))}",
            )

        patient_reference = args.get("patient_reference")
        phone_number = args.get("phone_number")

        if not patient_reference and not phone_number:
            return ToolExecutionResult(
                tool_name="verify_patient",
                success=False,
                error="Must provide either 'patient_reference' or 'phone_number' to verify patient.",
            )

        try:
            res = verify_patient_tool(
                db=db,
                patient_reference=str(patient_reference) if patient_reference else None,
                phone_number=str(phone_number) if phone_number else None,
            )
            return ToolExecutionResult(
                tool_name="verify_patient",
                success=True,
                data=res,
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name="verify_patient",
                success=False,
                error=str(exc),
            )


