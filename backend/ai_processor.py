import json
import re
from typing import Any, Dict, List, Optional

from backend.llm_client import LLMClient
from backend.rag_system import RAGSystem
from backend.vocabulary import Vocabulary

class AIProcessor:
    """Handles natural language processing and intent recognition with LLM integration."""

    def __init__(self, llm_client: LLMClient, rag_system: RAGSystem, vocabulary: Vocabulary):
        self.llm_client = llm_client
        self.rag_system = rag_system
        self.vocabulary = vocabulary

    def process_query(self, query: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Main query processing pipeline with caching."""
        # 1. Enhance query with RAG context
        rag_context = self.rag_system.retrieve_context(query)
        full_context = f"{context or ''}\n{rag_context}"

        # 2. Format prompt for LLM with a representative schema hint. The model
        # also knows the broader WAPI object catalog from training; the prompt
        # tells it other standard object types are valid too.
        formatted_prompt = self.llm_client.format_prompt(query, full_context, self._tools_schema_hint())

        # 3. Send request to LLM
        llm_response = self.llm_client.send_request(formatted_prompt)

        if "error" in llm_response:
            # Fallback processing if LLM fails
            return self.fallback_processing(query)

        # 4. Parse LLM response to extract intent and API calls.
        content = llm_response.get("content", "") or ""
        parsed_content = self._extract_json(content)

        # Multi-step plan: an ordered list of WAPI calls (e.g. create a network,
        # then a DHCP range inside it). Accept {"operations": [...]} or a bare
        # JSON array of call objects.
        operations = self._extract_operations(parsed_content)
        if operations is not None:
            if len(operations) == 1:
                return {"response_type": "api_call_proposal", "proposal": operations[0]}
            return {"response_type": "api_call_plan", "operations": operations}

        if isinstance(parsed_content, dict) and all(
            key in parsed_content for key in ("operation", "method", "parameters")
        ):
            return {"response_type": "api_call_proposal", "proposal": parsed_content}

        # Not a structured API-call proposal: return the natural-language reply.
        return {"response_type": "text", "content": content}

    @staticmethod
    def _is_call(obj: Any) -> bool:
        return isinstance(obj, dict) and "operation" in obj and "method" in obj

    @classmethod
    def _extract_operations(cls, parsed: Any) -> Optional[List[Dict[str, Any]]]:
        """Returns a list of call objects if `parsed` describes a multi-step plan."""
        if isinstance(parsed, dict) and isinstance(parsed.get("operations"), list):
            calls = [op for op in parsed["operations"] if cls._is_call(op)]
            return calls or None
        if isinstance(parsed, list):
            calls = [op for op in parsed if cls._is_call(op)]
            return calls or None
        return None

    @staticmethod
    def _extract_json(content: str) -> Optional[Any]:
        """Best-effort extraction of a JSON object from an LLM reply.

        Handles raw JSON, fenced ```json blocks, and JSON embedded in prose.
        Returns the parsed object, or None when no valid JSON is present.
        """
        if not content or not content.strip():
            return None

        candidates = []

        # Fenced code block: ```json ... ``` or ``` ... ```
        fence = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL | re.IGNORECASE)
        if fence:
            candidates.append(fence.group(1).strip())

        stripped = content.strip()
        candidates.append(stripped)

        # First balanced-looking {...} span in the text.
        brace = re.search(r"\{.*\}", stripped, re.DOTALL)
        if brace:
            candidates.append(brace.group(0))

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def revise_plan(self, pending_operations: List[Dict[str, Any]], instruction: str) -> Optional[List[Dict[str, Any]]]:
        """Apply a follow-up instruction to a previously-proposed plan.

        Handles "yes, but change the gateway to .254" style amendments and also
        plain new requests. Returns the revised list of call objects, or None if
        the reply is conversational (no WAPI operation) — let the caller fall
        back to a normal answer.
        """
        context = (
            "The user was just shown this proposed plan of Infoblox WAPI calls:\n"
            + json.dumps(pending_operations, indent=2)
            + "\nApply the user's instruction below to that plan and output the COMPLETE revised "
            "plan (keep unchanged calls as-is). If the instruction is an unrelated new request, "
            "output the plan for that instead."
        )
        prompt = self.llm_client.format_prompt(instruction, context, self._tools_schema_hint())
        resp = self.llm_client.send_request(prompt)
        if "error" in resp:
            return None
        parsed = self._extract_json(resp.get("content", "") or "")
        operations = self._extract_operations(parsed)
        if operations is not None:
            return operations
        if self._is_call(parsed):
            return [parsed]
        return None

    def synthesize_answer(self, query: str, operations: List[Dict[str, Any]],
                          results: List[Dict[str, Any]]) -> str:
        """Second LLM pass: turn executed WAPI results into a plain-English answer."""
        steps = []
        for op, res in zip(operations, results):
            data = res.get("data") if res.get("success") else {"error": res.get("error")}
            # Cap each result so a large list doesn't blow the context window.
            blob = json.dumps(data)
            if len(blob) > 6000:
                blob = blob[:6000] + " …(truncated)"
            steps.append({"call": {k: op.get(k) for k in ("operation", "method", "parameters")},
                          "result": blob})

        prompt = (
            f"User question: {query}\n\n"
            "You executed these Infoblox WAPI calls and received these results:\n"
            f"{json.dumps(steps, indent=2)}\n\n"
            "Answer the user's question concisely in plain English using ONLY this data. "
            "Do not output JSON or a WAPI call. If listing items, use bullets or a small table."
        )
        resp = self.llm_client.send_request(prompt)
        if "error" in resp:
            return "I executed the calls but could not synthesize an answer."
        return resp.get("content", "") or "(no answer)"

    def _tools_schema_hint(self) -> Dict[str, Any]:
        """A small, representative slice of the WAPI catalog for prompt grounding."""
        return {
            "network": {"fields": ["network", "network_view", "comment"]},
            "record:a": {"fields": ["name", "ipv4addr", "view", "ttl"]},
            "record:host": {"fields": ["name", "ipv4addrs", "configure_for_dns"]},
            "record:cname": {"fields": ["name", "canonical", "view"]},
            "range": {"fields": ["start_addr", "end_addr", "network"]},
            "fixedaddress": {"fields": ["ipv4addr", "mac", "network"]},
            "_note": "Other standard Infoblox WAPI object types are also valid.",
        }

    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Identifies network entities (IPs, hostnames, etc.) using vocabulary."""
        entities = {"wapi_objects": [], "wapi_fields": [], "wapi_enum_values": []}
        # Simple keyword matching for now
        for obj in self.vocabulary.get_terms("wapi_objects"):
            if obj.lower() in text.lower():
                entities["wapi_objects"].append(obj)
        for field in self.vocabulary.get_terms("wapi_fields"):
            if field.lower() in text.lower():
                entities["wapi_fields"].append(field)
        for enum_val in self.vocabulary.get_terms("wapi_enum_values"):
            if enum_val.lower() in text.lower():
                entities["wapi_enum_values"].append(enum_val)
        return entities

    def recognize_intent(self, query: str) -> Dict[str, Any]:
        """Maps query to WAPI operations with confidence scoring."""
        # This would typically involve LLM or more complex NLP models
        # For now, a very basic keyword-based intent recognition
        intent = {"action": "unknown", "confidence": 0.5}
        if any(keyword in query.lower() for keyword in ["create", "add", "new"]):
            intent["action"] = "create"
            intent["confidence"] = 0.7
        elif any(keyword in query.lower() for keyword in ["search", "find", "get", "show", "list"]):
            intent["action"] = "search"
            intent["confidence"] = 0.7
        elif any(keyword in query.lower() for keyword in ["update", "modify", "change"]):
            intent["action"] = "update"
            intent["confidence"] = 0.7
        elif any(keyword in query.lower() for keyword in ["delete", "remove"]):
            intent["action"] = "delete"
            intent["confidence"] = 0.7
        return intent

    def generate_api_calls(self, intent: Dict[str, Any], entities: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """Creates proposed API calls with validation."""
        # This is a highly simplified version. A real implementation would use LLM to generate structured calls.
        proposals = []
        if intent["action"] == "search" and entities["wapi_objects"]:
            for obj in entities["wapi_objects"]:
                proposals.append({
                    "operation": obj,
                    "method": "GET",
                    "parameters": {},
                    "description": f"Search for {obj} objects.",
                    "confidence": intent["confidence"]
                })
        return proposals

    def enhance_with_rag(self, query: str) -> str:
        """Adds relevant documentation context using the RAG system."""
        return "\n".join(self.rag_system.retrieve_context(query))

    def fallback_processing(self, query: str) -> Dict[str, Any]:
        """Keyword-based processing when LLM is unavailable or fails."""
        # Very basic fallback: just echo the query or provide a generic response
        return {"response_type": "text", "content": f"I'm sorry, I couldn't process that request fully. (Fallback: {query})"}
