from core.engine.event_bus import bus
from core.engine.llm_bridge import llm_bridge
from core.engine.context_builder import context_distiller, prompt_builder
from core.engine.decision_engine import decision_engine
from core.state.manager import state_manager
from core.state.memory import memory_manager
from core.state.short_term import short_term_memory
from core.utils.logger import logger

class Brain:
    def __init__(self):
        bus.subscribe("AI_TRIGGERED", self.on_ai_triggered)
        bus.subscribe("VOICE_INPUT_RECEIVED", self.on_voice_input)

    def on_voice_input(self, text):
        logger.log_event("BRAIN_VOICE_INPUT", {"text": text})
        self.on_ai_triggered({"type": "VOICE_COMMAND", "confidence": 1.0, "text": text})

    def on_ai_triggered(self, trigger_data):
        state = state_manager.get_state()
        
        # 1. Decision Gating
        if not decision_engine.should_call_ai(trigger_data, state):
            bus.publish("SAFE_NO_ACTION")
            return

        # 2. Context & Memory
        distilled = context_distiller.distill(state)
        memories = memory_manager.retrieve(state.app, str(distilled))
        
        # 3. Prompting
        prompt = prompt_builder.build(distilled, trigger_data["type"])
        if memories:
            prompt += f"\n\nPAST RELEVANT MEMORIES:\n{memories}"
            
        # 4. LLM Call
        response = llm_bridge.generate(prompt)
        
        if not response:
            logger.logger.error("Brain: LLM failed to provide response")
            bus.publish("SAFE_NO_ACTION")
            return

        # 5. Response Mode & Storage
        mode = decision_engine.get_response_mode(response.get("confidence", 0))
        response["mode"] = mode
        
        if mode != "IGNORE":
            memory_manager.store(state.app, str(distilled), response)
            short_term_memory.add({"context": distilled, "response": response})
            bus.publish("BRAIN_RESPONDED", response)
            logger.log_event("BRAIN_DECISION", response)
        else:
            bus.publish("SAFE_NO_ACTION")

brain = Brain()
