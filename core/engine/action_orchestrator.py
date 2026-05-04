import time
import threading
import json
import os
from datetime import datetime
from core.engine.event_bus import bus
from core.config import sys_config
from core.engine.executor import executor
from core.engine.action_state import action_state
from core.engine.action_safety import action_safety
from core.engine.action_verifier import action_verifier
from core.engine.plan_validator import plan_validator
from core.engine.response_schema import response_schema
from core.utils.logger import logger

class ActionOrchestrator:
    # All known action types -- add new ones here, they route to executor automatically
    KNOWN_ACTIONS = {
        "click", "click_text", "drag", "type", "hotkey", "scroll", "switch", "launch",
        "open_url", "cmd", "create_skill", "read_file", "list_dir",
        "write_file", "extract_clipboard", "listen_audio", "ocr_screen",
        "blender_python", "blender_create_scene", "blender_bridge_status",
        "blender_open_import_menu", "blender_import_file"
    }

    def __init__(self):
        bus.subscribe("ACTION_REQUESTED", self.on_action_requested)
        self.confirm_event = threading.Event()
        bus.subscribe("CONFIRM_HOTKEY", lambda d: self.confirm_event.set())

    def on_action_requested(self, data):
        logger.log_event("ACTION_REQUESTED", {
            "status": data.get("status"),
            "actions": data.get("actions", [])
        })

        if not action_state.start_action("orchestration"):
            logger.log_event("ACTION_SKIPPED_BUSY", {
                "current_action": action_state.current_action,
                "requested_actions": data.get("actions", [])
            })
            return

        def _run():
            try:
                self.confirm_event.clear()
                
                if sys_config.is_observation_only:
                    logger.log_event("OBSERVATION_MODE_BLOCK", data)
                    return

                # Wait for confirmation if required
                if sys_config.get("action_confirmation_required"):
                    logger.log_event("WAITING_FOR_CONFIRMATION", data)
                    if not self.confirm_event.wait(timeout=15.0):
                        logger.log_event("ACTION_ABORTED", {"reason": "Timeout"})
                        bus.publish("ACTION_ABORTED", {"reason": "Confirmation timeout"})
                        return

                # Resolve active window/app for safety context
                try:
                    from core.state.manager import state_manager
                    st = state_manager.get_state()
                    active_window = st.window or ""
                    active_app = st.app or ""
                except Exception:
                    active_window = ""
                    active_app = ""

                # ── Trace Collection ──
                trace_data = {
                    "timestamp": datetime.now().isoformat(),
                    "user_command": "",
                    "active_app": active_app,
                    "active_window": active_window,
                    "rag_context_titles": [],
                    "llm_response": {},
                    "schema_result": {},
                    "plan_result": {},
                    "safety_results": [],
                    "dry_run_actions": [],
                    "would_execute_count": 0,
                    "blocked_actions": [],
                    "final_status": "in_progress"
                }

                # Try to get user command and RAG titles
                try:
                    from core.state.short_term import short_term_memory
                    history = short_term_memory.get_history()
                    if history:
                        trace_data["user_command"] = history[-1].get("command", "")
                    
                    # Truncate large llm message in trace
                    msg = data.get("message", "")
                    trace_data["llm_response"] = {**data, "message": msg[:200] + "..." if len(msg) > 200 else msg}
                except Exception:
                    pass

                # -- Schema validation gate (FIRST in pipeline) --
                try:
                    schema_result = response_schema.validate(data)
                    trace_data["schema_result"] = {
                        "valid": schema_result["valid"],
                        "reason": schema_result["reason"],
                        "removed_actions": schema_result["removed_actions"]
                    }
                    if not schema_result["valid"]:
                        trace_data["final_status"] = "failed"
                        self._export_trace(trace_data)
                        logger.log_event("RESPONSE_SCHEMA_INVALID", {
                            "reason": schema_result["reason"],
                        })
                        bus.publish("RESPONSE_SCHEMA_INVALID", {
                            "reason": schema_result["reason"],
                        })
                        try:
                            from core.state.short_term import short_term_memory
                            short_term_memory.add_system_context(
                                f"RESPONSE_SCHEMA_INVALID: {schema_result['reason'][:300]}. "
                                f"Fix your JSON response format."
                            )
                        except Exception:
                            pass
                        return
                    # Use the normalized response from here on
                    normalized = schema_result["response"]
                except Exception as _se:
                    logger.logger.error(f"Orchestrator: Schema validation error (non-fatal): {_se}")
                    normalized = data  # Fall through with raw data

                actions = normalized.get("actions", [])
                confidence = normalized.get("confidence", 1.0)

                # ── Plan validation gate ──
                try:
                    plan_result = plan_validator.validate(normalized)
                    trace_data["plan_result"] = {
                        "valid": plan_result["valid"],
                        "reason": plan_result["reason"]
                    }
                    if not plan_result["valid"]:
                        trace_data["final_status"] = "failed"
                        self._export_trace(trace_data)
                        logger.log_event("PLAN_VALIDATION_FAILED", {
                            "reason": plan_result["reason"],
                        })
                        bus.publish("PLAN_VALIDATION_FAILED", {
                            "reason": plan_result["reason"],
                        })
                        try:
                            from core.state.short_term import short_term_memory
                            short_term_memory.add_system_context(
                                f"PLAN_VALIDATION_FAILED: {plan_result['reason'][:300]}. "
                                f"Include a 'plan' field listing your steps before actions."
                            )
                        except Exception:
                            pass
                        return
                    if plan_result.get("warnings"):
                        for w in plan_result["warnings"]:
                            logger.logger.warning(f"PlanValidator: {w}")
                except Exception as _pv_err:
                    logger.logger.error(f"Orchestrator: Plan validation error (non-fatal): {_pv_err}")

                executed_actions = []
                for action in actions:
                    a_type = action.get("type")
                    
                    if a_type not in self.KNOWN_ACTIONS:
                        logger.logger.warning(f"Unknown action type: {a_type}")
                        continue
                    
                    # ── Safety gate ──
                    verdict = action_safety.validate(
                        action,
                        confidence=confidence,
                        active_window=active_window,
                        active_app=active_app,
                    )
                    trace_data["safety_results"].append({
                        "type": a_type,
                        "allowed": verdict["allowed"],
                        "risk": verdict["risk"],
                        "reason": verdict["reason"]
                    })

                    if not verdict["allowed"]:
                        trace_data["blocked_actions"].append({"type": a_type, "reason": verdict["reason"]})
                        bus.publish("ACTION_ABORTED", {
                            "reason": verdict["reason"],
                            "action": a_type,
                            "risk": verdict["risk"],
                        })
                        # Feed back into LLM memory so it knows why we refused
                        try:
                            from core.state.short_term import short_term_memory
                            short_term_memory.add_system_context(
                                f"ACTION_BLOCKED [{verdict['risk']}]: {a_type} — {verdict['reason'][:200]}"
                            )
                        except Exception:
                            pass
                        continue
                    
                    # ── Dry Run Logic ──
                    if sys_config.get("dry_run_enabled"):
                        logger.logger.info(f"DRY RUN: Would execute {a_type}: {action}")
                        logger.log_event("DRY_RUN_ACTION", {"type": a_type, "action": action})
                        bus.publish("DRY_RUN_ACTION", {"type": a_type, "action": action})
                        
                        trace_data["dry_run_actions"].append(action)
                        trace_data["would_execute_count"] += 1

                        # Feed back into memory
                        try:
                            from core.state.short_term import short_term_memory
                            short_term_memory.add_system_context(
                                f"DRY_RUN: Action {a_type} would have been executed."
                            )
                        except Exception:
                            pass
                            
                        # Show highlight if it's a UI action with coordinates or target
                        if sys_config.get("dry_run_show_overlay"):
                            if a_type in ["click", "click_text", "drag"]:
                                bus.publish("HIGHLIGHT_REQUESTED", action)
                        
                        executed_actions.append(action)
                        # Skip execution and verification
                        continue

                    # ── Capture baseline frame for verification ──
                    from core.vision.live_perception import live_perception
                    frame_before = live_perception.get_latest_frame()

                    # ── Execute ──
                    executor.execute_single(action)
                    executed_actions.append(action)
                    
                    # ── Post-action verification ──
                    try:
                        vresult = action_verifier.verify(action, frame_before)
                        if vresult["success"]:
                            logger.log_event("ACTION_VERIFIED", {
                                "type": a_type, "reason": vresult["reason"]
                            })
                        else:
                            logger.log_event("ACTION_VERIFICATION_FAILED", {
                                "type": a_type,
                                "reason": vresult["reason"],
                                "evidence": vresult.get("evidence", {}),
                            })
                            bus.publish("ACTION_VERIFY_FAILED", {
                                "action": a_type,
                                "reason": vresult["reason"],
                            })
                            try:
                                from core.state.short_term import short_term_memory
                                short_term_memory.add_system_context(
                                    f"ACTION_VERIFY_FAILED: {a_type} — {vresult['reason'][:200]}"
                                )
                            except Exception:
                                pass
                            
                            # Optional single retry
                            if (
                                vresult.get("should_retry")
                                and sys_config.get("verification_retry_enabled")
                            ):
                                max_retries = sys_config.get("max_verification_retries") or 1
                                for retry_i in range(max_retries):
                                    logger.logger.info(
                                        f"Orchestrator: Retrying '{a_type}' (attempt {retry_i + 1}/{max_retries})"
                                    )
                                    import time as _time
                                    _time.sleep(0.4)
                                    frame_retry = live_perception.get_latest_frame()
                                    executor.execute_single(action)
                                    rv = action_verifier.verify(action, frame_retry)
                                    if rv["success"]:
                                        logger.log_event("ACTION_VERIFIED", {
                                            "type": a_type, "reason": f"Retry {retry_i+1} succeeded"
                                        })
                                        break
                    except Exception as _ve:
                        logger.logger.error(f"Orchestrator: Verification error (non-fatal): {_ve}")

                # Finalize Trace
                if sys_config.get("dry_run_enabled"):
                    if trace_data["blocked_actions"]:
                        trace_data["final_status"] = "blocked"
                    else:
                        trace_data["final_status"] = "simulated"
                    self._export_trace(trace_data)

                logger.log_event("ACTION_SEQUENCE_COMPLETED", {
                    "total": len(actions),
                    "executed": len(executed_actions),
                    "status": data.get("status")
                })
                    
            finally:
                action_state.stop_action()
                
            # Trigger the agentic verification loop if the AI indicated it's still in progress
            if data.get("status") == "in_progress":
                logger.logger.info("Actions complete, triggering verification loop...")
                time.sleep(1.0) # Wait for UI to settle
                bus.publish("AUTONOMOUS_LOOP_TRIGGER", data)

        threading.Thread(target=_run, daemon=True).start()

    def _export_trace(self, trace_data):
        if not sys_config.get("dry_run_trace_enabled"):
            return
            
        try:
            trace_dir = os.path.join("data", "traces")
            if not os.path.exists(trace_dir):
                os.makedirs(trace_dir, exist_ok=True)
                
            filename = f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(trace_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(trace_data, f, indent=2)
                
            logger.logger.info(f"Dry-run trace exported: {filepath}")
            bus.publish("TRACE_EXPORTED", {"path": filepath, "filename": filename})
        except Exception as e:
            logger.logger.error(f"Failed to export dry-run trace: {e}")

action_orchestrator = ActionOrchestrator()
