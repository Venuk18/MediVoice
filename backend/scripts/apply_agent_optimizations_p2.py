with open("backend/app/agent/adapters.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Target block right before tool_declarations in plan_and_respond
old_before_tools = """                    return AgentAction(
                        reply=format_localized_message(
                            lang, "checking_slots", doctor_name=session_state.draft.doctor_name or "the doctor"
                        ),
                        tool_call=slot_intent,
                    )

        tool_declarations = self._build_tool_declarations(available_tools)"""

new_deterministic_block = """                    return AgentAction(
                        reply=format_localized_message(
                            lang, "checking_slots", doctor_name=session_state.draft.doctor_name or "the doctor"
                        ),
                        tool_call=slot_intent,
                    )

        # Section 2 Optimization: Fast deterministic context-aware routing for predictable hospital requests
        doc_search_term = self._detect_doctor_query(msg)
        spec_query = detect_specialty_query(msg, current_specialty=session_state.draft.specialty)

        is_predictable_specialty_or_doctor = (
            (doc_search_term is not None or spec_query is not None)
            and not emergency_kind
            and not is_insurance_inquiry(msg)
            and not is_lab_report_inquiry(msg)
            and not session_state.draft.is_complete()
            and (
                bool(re.search(r"\\b(find|search|see|meet|consult|need|want|book|schedule|show|check|looking\\s+for|thinking\\s+to\\s+meet|appointment\\s+with|doctor|specialist|physician)\\b", msg.lower()))
                or len(msg.split()) <= 5
            )
        )

        if is_predictable_specialty_or_doctor and "search_doctors" in available_tools and tool_executor is not None:
            target_dept = doc_search_term or spec_query
            if target_dept:
                search_intent = ToolCallIntent(
                    tool_name="search_doctors",
                    arguments={"specialty_or_department": target_dept},
                )
                t_t0 = time.perf_counter()
                search_res = tool_executor(search_intent)
                tool_router_ms += (time.perf_counter() - t_t0) * 1000
                if search_res.success and search_res.data:
                    docs = search_res.data
                    is_doc_specific = (doc_search_term is not None or len(docs) == 1)
                    if is_doc_specific and docs:
                        chosen = docs[0]
                        session_state.draft.doctor_id = chosen["doctor_id"]
                        session_state.draft.doctor_name = chosen["display_name"]
                        session_state.draft.specialty = chosen["specialty"]
                        session_state.pending_action = None
                        session_state.pending_action_data = {}

                        if "get_available_slots" in available_tools:
                            slot_intent = ToolCallIntent(
                                tool_name="get_available_slots",
                                arguments={"doctor_id": chosen["doctor_id"]},
                            )
                            t_s0 = time.perf_counter()
                            slot_res = tool_executor(slot_intent)
                            tool_router_ms += (time.perf_counter() - t_s0) * 1000
                            if slot_res.success and slot_res.data:
                                slots = slot_res.data
                                slot_lines = "\\n".join([f"• {format_human_slot_time(s['start_time'])} (Slot ID: {s['slot_id']})" for s in slots[:4]])
                                reply_text = format_localized_message(
                                    lang,
                                    "selected_doctor_slots",
                                    doctor_name=chosen["display_name"],
                                    specialty=chosen["specialty"],
                                    slot_lines=slot_lines,
                                    example_slot=slots[0]["slot_id"],
                                )
                                self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                                return AgentAction(reply=reply_text, tool_call=None)

                        reply_text = format_localized_message(
                            lang,
                            "doctor_found_consult_or_more",
                            doctor_name=chosen["display_name"],
                            specialty=chosen["specialty"],
                        )
                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                        return AgentAction(reply=reply_text, tool_call=None)
                    elif docs:
                        spec_plural = get_specialist_plural(lang, docs[0].get("specialty", target_dept))
                        session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
                        session_state.pending_action_data = {
                            "doctor_id": docs[0].get("doctor_id"),
                            "doctor_name": docs[0].get("display_name"),
                            "specialty": docs[0].get("specialty"),
                        }
                        doc_list_str = "\\n".join([f"• {d['display_name']} — {d['specialty']}" for d in docs[:3]])
                        reply_text = format_localized_message(
                            lang,
                            "found_specialists_recommend",
                            count=len(docs),
                            specialist_plural=spec_plural,
                            doc_list=doc_list_str,
                            recommend_name=docs[0]["display_name"],
                        )
                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                        return AgentAction(reply=reply_text, tool_call=None)

        # Fast Deterministic Slot Inquiry for Selected Doctor
        if is_slot_inquiry(msg) and session_state.draft.doctor_id and "get_available_slots" in available_tools and tool_executor is not None:
            t_s0 = time.perf_counter()
            slot_res = tool_executor(
                ToolCallIntent(
                    tool_name="get_available_slots",
                    arguments={"doctor_id": session_state.draft.doctor_id, "time_range": None},
                )
            )
            tool_router_ms += (time.perf_counter() - t_s0) * 1000
            if slot_res.success and slot_res.data:
                slots = slot_res.data
                slot_lines = "\\n".join([f"• {format_human_slot_time(s['start_time'])} (Slot ID: {s['slot_id']})" for s in slots[:4]])
                reply_text = format_localized_message(
                    lang,
                    "available_slots",
                    doctor_name=session_state.draft.doctor_name or "the doctor",
                    slot_lines=slot_lines,
                    example_slot=slots[0]["slot_id"],
                )
                self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                return AgentAction(reply=reply_text, tool_call=None)

        tool_declarations = self._build_tool_declarations(available_tools)"""

if old_before_tools.replace("\n", "\r\n") in content:
    content = content.replace(old_before_tools.replace("\n", "\r\n"), new_deterministic_block.replace("\n", "\r\n"))
elif old_before_tools in content:
    content = content.replace(old_before_tools, new_deterministic_block)
else:
    print("Warning: old_before_tools not found")

# 2. Timing the provider call and short-circuiting follow-up Gemini calls for simple tools
old_round_call = """                raw_response = self._call_provider(payload)
                model_content, text_reply, tool_intent = self._parse_candidate_parts(raw_response)"""

new_round_call = """                t_provider_start = time.perf_counter()
                raw_response = self._call_provider(payload)
                provider_elapsed = (time.perf_counter() - t_provider_start) * 1000
                if rounds == 1:
                    initial_gemini_request_ms = provider_elapsed
                else:
                    followup_gemini_request_ms += provider_elapsed
                gemini_calls_count += 1
                model_content, text_reply, tool_intent = self._parse_candidate_parts(raw_response)"""

if old_round_call.replace("\n", "\r\n") in content:
    content = content.replace(old_round_call.replace("\n", "\r\n"), new_round_call.replace("\n", "\r\n"))
elif old_round_call in content:
    content = content.replace(old_round_call, new_round_call)
else:
    print("Warning: old_round_call not found")

# 3. Short-circuit follow-up call after tool execution for simple tools
old_tool_exec_block = """                # Execute tool via the provided restricted tool executor callback
                tool_result = tool_executor(tool_intent)

                # Append model's exact content turn (preserving thoughtSignature) and functionResponse turn
                contents.append(model_content)"""

new_tool_exec_block = """                # Execute tool via the provided restricted tool executor callback
                t_tool_start = time.perf_counter()
                tool_result = tool_executor(tool_intent)
                tool_router_ms += (time.perf_counter() - t_tool_start) * 1000

                # Section 2 Optimization: For simple tool results, generate concise responses directly
                # from validated backend results instead of making an unnecessary second Gemini request!
                if tool_result.success and tool_intent.tool_name in (
                    "search_doctors", "get_available_slots", "search_hospital_insurance", "check_lab_report_status"
                ):
                    if tool_intent.tool_name == "search_doctors" and tool_result.data:
                        docs = tool_result.data
                        if len(docs) == 1:
                            chosen = docs[0]
                            session_state.draft.doctor_id = chosen["doctor_id"]
                            session_state.draft.doctor_name = chosen["display_name"]
                            session_state.draft.specialty = chosen["specialty"]
                            if "get_available_slots" in available_tools:
                                t_s0 = time.perf_counter()
                                slot_res = tool_executor(ToolCallIntent(tool_name="get_available_slots", arguments={"doctor_id": chosen["doctor_id"]}))
                                tool_router_ms += (time.perf_counter() - t_s0) * 1000
                                if slot_res.success and slot_res.data:
                                    slots = slot_res.data
                                    slot_lines = "\\n".join([f"• {format_human_slot_time(s['start_time'])} (Slot ID: {s['slot_id']})" for s in slots[:4]])
                                    concise_reply = format_localized_message(
                                        lang, "selected_doctor_slots",
                                        doctor_name=chosen["display_name"],
                                        specialty=chosen["specialty"],
                                        slot_lines=slot_lines,
                                        example_slot=slots[0]["slot_id"],
                                    )
                                    self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                                    return AgentAction(reply=concise_reply, tool_call=None)
                            concise_reply = format_localized_message(lang, "doctor_found_consult_or_more", doctor_name=chosen["display_name"], specialty=chosen["specialty"])
                            self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                            return AgentAction(reply=concise_reply, tool_call=None)
                        elif docs:
                            spec_plural = get_specialist_plural(lang, docs[0].get("specialty", tool_intent.arguments.get("specialty_or_department", "Specialist")))
                            session_state.pending_action = "SHOW_SLOTS_FOR_DOCTOR"
                            session_state.pending_action_data = {
                                "doctor_id": docs[0].get("doctor_id"),
                                "doctor_name": docs[0].get("display_name"),
                                "specialty": docs[0].get("specialty"),
                            }
                            doc_list_str = "\\n".join([f"• {d['display_name']} — {d['specialty']}" for d in docs[:3]])
                            concise_reply = format_localized_message(lang, "found_specialists_recommend", count=len(docs), specialist_plural=spec_plural, doc_list=doc_list_str, recommend_name=docs[0]["display_name"])
                            self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                            return AgentAction(reply=concise_reply, tool_call=None)

                    elif tool_intent.tool_name == "get_available_slots" and tool_result.data:
                        slots = tool_result.data
                        slot_lines = "\\n".join([f"• {format_human_slot_time(s['start_time'])} (Slot ID: {s['slot_id']})" for s in slots[:4]])
                        concise_reply = format_localized_message(
                            lang, "available_slots",
                            doctor_name=session_state.draft.doctor_name or "the doctor",
                            slot_lines=slot_lines,
                            example_slot=slots[0]["slot_id"],
                        )
                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                        return AgentAction(reply=concise_reply, tool_call=None)

                    elif tool_intent.tool_name == "search_hospital_insurance" and isinstance(tool_result.data, dict):
                        concise_reply = format_insurance_search_reply(lang, tool_result.data, user_message=msg)
                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                        return AgentAction(reply=concise_reply, tool_call=None)

                    elif tool_intent.tool_name == "check_lab_report_status" and isinstance(tool_result.data, dict):
                        concise_reply = format_lab_verification_reply(lang, tool_result.data)
                        self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                        return AgentAction(reply=concise_reply, tool_call=None)

                # Append model's exact content turn (preserving thoughtSignature) and functionResponse turn
                contents.append(model_content)"""

if old_tool_exec_block.replace("\n", "\r\n") in content:
    content = content.replace(old_tool_exec_block.replace("\n", "\r\n"), new_tool_exec_block.replace("\n", "\r\n"))
elif old_tool_exec_block in content:
    content = content.replace(old_tool_exec_block, new_tool_exec_block)
else:
    print("Warning: old_tool_exec_block not found")

# 4. Make sure tool_intent is None return path records timings
old_no_tool_return = """                if tool_intent is None:
                    final_text = accumulated_text or build_localized_prompt_for_current_state(session_state)
                    final_text = ensure_response_in_session_language(final_text, session_state, msg)
                    final_text = with_urgent_guidance_if_needed(
                        lang, final_text, msg, session_state.draft.reason_category
                    )
                    return AgentAction(reply=final_text, tool_call=None)"""

new_no_tool_return = """                if tool_intent is None:
                    final_text = accumulated_text or build_localized_prompt_for_current_state(session_state)
                    final_text = ensure_response_in_session_language(final_text, session_state, msg)
                    final_text = with_urgent_guidance_if_needed(
                        lang, final_text, msg, session_state.draft.reason_category
                    )
                    self._record_timings(initial_gemini_request_ms, tool_router_ms, followup_gemini_request_ms, gemini_calls_count, t_start)
                    return AgentAction(reply=final_text, tool_call=None)"""

if old_no_tool_return.replace("\n", "\r\n") in content:
    content = content.replace(old_no_tool_return.replace("\n", "\r\n"), new_no_tool_return.replace("\n", "\r\n"))
elif old_no_tool_return in content:
    content = content.replace(old_no_tool_return, new_no_tool_return)

with open("backend/app/agent/adapters.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Part 2: adapters.py updated with deterministic routing and single-turn response.")

