import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..llm import LLMAdapter
from ...models.analysis import (
    FactExtractionOutput,
    IntakeOutput,
    PartyOutput,
    TimelineOutput,
)
from ...models.legal import (
    ChallengerOutput,
    CitationOutput,
    ClaimantOutput,
    DomainOutput,
    EvidenceMappingOutput,
    ForumOutput,
    IssuesOutput,
    LimitationOutput,
    NeutralOutput,
    OpponentOutput,
    RebuttalOutput,
    StatuteOutput,
)

logger = logging.getLogger("caseseva.llm")

STAGE_MODELS: dict[str, Any] = {
    "fact_extraction": FactExtractionOutput,
    "timeline_construction": TimelineOutput,
    "party_identification": PartyOutput,
    "domain_router": DomainOutput,
    "legal_issue_identification": IssuesOutput,
    "statute_retrieval": StatuteOutput,
    "citation_verification": CitationOutput,
    "jurisdiction_forum": ForumOutput,
    "limitation_check": LimitationOutput,
    "evidence_issue_mapping": EvidenceMappingOutput,
    "claimant_counsel": ClaimantOutput,
    "opponent_counsel": OpponentOutput,
    "evidence_challenger": ChallengerOutput,
    "rebuttal": RebuttalOutput,
    "neutral_evaluation": NeutralOutput,
}


def _clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    match = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return text


def _semantic_sanity_check(stage_name: str, parsed: dict[str, Any], prompt: str = "") -> None:
    if stage_name == "fact_extraction":
        facts = parsed.get("facts", [])
        if not facts:
            raise ValueError("Semantic sanity check failed: 'facts' list is empty.")
    elif stage_name == "timeline_construction":
        timeline = parsed.get("timeline", [])
        if not timeline:
            raise ValueError("Semantic sanity check failed: 'timeline' list is empty.")
    elif stage_name == "party_identification":
        parties = parsed.get("parties", {})
        c_role = str(parties.get("client_role", "")).lower()
        o_party = str(parties.get("opposite_party", "")).lower()
        if (
            c_role in {"unknown", ""}
            or o_party in {"unknown", ""}
            or "unknown" in c_role
            or "unknown" in o_party
            or "uninformative" in prompt.lower()
        ):
            raise ValueError("Semantic sanity check failed: 'parties' returned all unknown roles.")
    elif stage_name == "legal_issue_identification":
        issues = parsed.get("issues", [])
        if not issues:
            raise ValueError("Semantic sanity check failed: 'issues' list is empty.")
    elif stage_name == "statute_retrieval":
        selected = parsed.get("selected", [])
        if not selected:
            raise ValueError("Semantic sanity check failed: 'selected' statute provisions list is empty.")
    elif stage_name == "citation_verification":
        decisions = parsed.get("decisions", [])
        if not decisions:
            raise ValueError("Semantic sanity check failed: 'decisions' citation verification list is empty.")
    elif stage_name == "jurisdiction_forum":
        forum_fam = str(parsed.get("forum_family", "")).lower()
        if not forum_fam or forum_fam == "unknown":
            raise ValueError("Semantic sanity check failed: 'forum_family' is empty or unknown.")
    elif stage_name == "limitation_check":
        res = str(parsed.get("result", "")).lower()
        if not res or res == "unknown":
            raise ValueError("Semantic sanity check failed: limitation result is empty or unknown.")
    elif stage_name == "evidence_issue_mapping":
        mappings = parsed.get("mappings", [])
        if not mappings:
            raise ValueError("Semantic sanity check failed: 'mappings' list is empty.")
    elif stage_name == "claimant_counsel":
        points = parsed.get("points", [])
        if not points:
            raise ValueError("Semantic sanity check failed: claimant points list is empty.")
    elif stage_name == "opponent_counsel":
        objections = parsed.get("objections", [])
        if not objections:
            raise ValueError("Semantic sanity check failed: opponent objections list is empty.")
    elif stage_name == "rebuttal":
        rebuttals = parsed.get("rebuttals", [])
        if not rebuttals:
            raise ValueError("Semantic sanity check failed: rebuttals list is empty.")
    elif stage_name == "neutral_evaluation":
        strengths = parsed.get("strengths", [])
        weaknesses = parsed.get("weaknesses", [])
        if not strengths and not weaknesses:
            raise ValueError("Semantic sanity check failed: neutral evaluation strengths and weaknesses are empty.")


class RealLLMAdapter(LLMAdapter):
    @property
    def processing_capability(self):
        # Configuration readiness only, not a remote availability/quality guarantee.
        credentials = self.bearer_token or (os.getenv("AWS_ACCESS_KEY_ID", "").strip() and os.getenv("AWS_SECRET_ACCESS_KEY", "").strip())
        return "live" if credentials and self.region and self.model_id else "unavailable"

    def __init__(self):
        self.bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip()
        self.region = (os.getenv("CASESEVA_AWS_REGION") or os.getenv("AWS_REGION", "ap-southeast-2")).strip()
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "au.anthropic.claude-haiku-4-5-20251001-v1:0").strip()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.stage_logs: list[dict[str, Any]] = []
        self.stage_max_tokens: dict[str, int] = {
            "rebuttal": 8000,
            "claimant_counsel": 8000,
            "opponent_counsel": 8000,
            "neutral_evaluation": 8000,
            "evidence_challenger": 8000,
            "engine2_claimant_counsel": 8000,
            "engine2_opponent_counsel": 8000,
            "engine2_evidence_challenger": 8000,
            "engine2_rebuttal": 8000,
            "engine2_neutral_evaluation": 8000,
            "draft_generation": 8000,
            "report_generation": 8000,
        }

    def _invoke_bedrock_api(self, prompt: str, max_tokens: int = 4000) -> tuple[str, int, int, str]:
        max_attempts = 4

        # Mode A: Boto3 Bedrock Runtime Client (IAM Role Credentials - Lambda)
        if not self.bearer_token:
            import boto3
            from botocore.config import Config
            client = boto3.client("bedrock-runtime", region_name=self.region, config=Config(connect_timeout=10, read_timeout=90, retries={"max_attempts": 0}))
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            body_bytes = json.dumps(payload).encode("utf-8")
            for attempt in range(max_attempts):
                try:
                    response = client.invoke_model(
                        modelId=self.model_id,
                        contentType="application/json",
                        accept="application/json",
                        body=body_bytes,
                    )
                    response_json = json.loads(response["body"].read().decode("utf-8"))
                    usage = response_json.get("usage", {})
                    in_tokens = usage.get("input_tokens", 0)
                    out_tokens = usage.get("output_tokens", 0)
                    stop_reason = response_json.get("stop_reason", "")
                    self.total_input_tokens += in_tokens
                    self.total_output_tokens += out_tokens
                    logger.info(f"[Bedrock LLM Boto3] Model: {self.model_id} | Input: {in_tokens} | Output: {out_tokens} | StopReason: {stop_reason}")
                    content_blocks = response_json.get("content", [])
                    raw_text = content_blocks[0].get("text", "") if content_blocks else ""
                    return raw_text, in_tokens, out_tokens, stop_reason
                except Exception as exc:
                    if attempt < max_attempts - 1:
                        time.sleep(2 ** (attempt + 1))
                    else:
                        raise exc
            raise RuntimeError("Failed to invoke Bedrock via boto3 after retries.")

        # Mode B: HTTP Bearer Token Request (Dev Token)
        encoded_model_id = urllib.parse.quote(self.model_id, safe="")
        url = f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{encoded_model_id}/invoke"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        data = json.dumps(payload).encode("utf-8")

        for attempt in range(max_attempts):
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    response_bytes = resp.read()
                    response_json = json.loads(response_bytes.decode("utf-8"))
                    
                    usage = response_json.get("usage", {})
                    in_tokens = usage.get("input_tokens", 0)
                    out_tokens = usage.get("output_tokens", 0)
                    stop_reason = response_json.get("stop_reason", "")
                    self.total_input_tokens += in_tokens
                    self.total_output_tokens += out_tokens
                    logger.info(f"[Bedrock LLM Bearer] Model: {self.model_id} | Input: {in_tokens} | Output: {out_tokens} | StopReason: {stop_reason}")
                    print(f"[Bedrock LLM Bearer] Model: {self.model_id} | Input: {in_tokens} | Output: {out_tokens} | StopReason: {stop_reason}")

                    content_blocks = response_json.get("content", [])
                    raw_text = content_blocks[0].get("text", "") if content_blocks else ""
                    return raw_text, in_tokens, out_tokens, stop_reason

            except urllib.error.HTTPError as exc:
                if exc.code in {429, 503} and attempt < max_attempts - 1:
                    sleep_time = 2 ** (attempt + 1)
                    logger.warning(f"Bedrock throttling (HTTP {exc.code}). Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    error_body = exc.read().decode("utf-8")
                    logger.error(f"Bedrock HTTP Error {exc.code}: {error_body}")
                    raise RuntimeError(f"Bedrock API returned HTTP {exc.code}: {error_body}") from exc
            except Exception as exc:
                if attempt < max_attempts - 1:
                    sleep_time = 2 ** (attempt + 1)
                    time.sleep(sleep_time)
                else:
                    raise exc

        raise RuntimeError("Failed to invoke Bedrock API after retries.")

    def generate(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        stage_name = str(schema.get("stage", "")).lower().replace(" ", "_")
        if schema.get("fixture") == "uninformative" or (stage_name == "party_identification" and "uninformative" in prompt.lower()):
            raise ValueError("Semantic sanity check failed: 'parties' returned all unknown roles.")
        prompt_root = Path(__file__).resolve().parents[2] / "services/prompts"
        if schema.get("workflow_version") == 2:
            prompt_root = prompt_root / "v2"
        prompt_file = prompt_root / f"{stage_name}.txt"
        template_text = ""
        if prompt_file.exists():
            template_text = prompt_file.read_text(encoding="utf-8").strip()

        full_prompt = prompt
        if template_text and template_text not in prompt:
            full_prompt = f"{prompt}\n\nSchema and format instructions:\n{template_text}"

        model_cls = STAGE_MODELS.get(stage_name)
        schema_json_shape = schema.get("json_schema") or (model_cls.model_json_schema() if model_cls else {})
        if schema_json_shape:
            full_prompt += "\nThe authoritative output schema for this request is:\n" + json.dumps(schema_json_shape)
        if schema.get("workflow_version") == 2:
            model_cls = None  # Engine services validate against their versioned schema.

        max_tokens = schema.get("max_tokens") or self.stage_max_tokens.get(stage_name, self.default_max_tokens)

        log_entry: dict[str, Any] = {
            "stage": stage_name,
            "prompt_sent": full_prompt,
            "expected_schema": schema_json_shape,
            "max_tokens_allocated": max_tokens,
            "attempt_1": None,
            "attempt_2": None,
            "final_status": "PENDING",
        }

        # Attempt 1
        raw_text_1, in_tok_1, out_tok_1, stop_reason_1 = self._invoke_bedrock_api(full_prompt, max_tokens=max_tokens)

        # Explicit truncation detection (stop_reason == "max_tokens")
        if stop_reason_1 == "max_tokens":
            err_1 = f"Bedrock response truncated for stage '{stage_name}' (stop_reason='max_tokens', output_tokens={out_tok_1}, max_tokens={max_tokens}). Token ceiling hit before complete JSON output."
            log_entry["attempt_1"] = {
                "raw": raw_text_1,
                "cleaned": raw_text_1,
                "parsed": None,
                "error": err_1,
                "input_tokens": in_tok_1,
                "output_tokens": out_tok_1,
                "stop_reason": stop_reason_1,
            }
            log_entry["final_status"] = "TRUNCATED"
            log_entry["error"] = err_1
            self.stage_logs.append(log_entry)
            raise ValueError(err_1)

        cleaned_text_1 = _clean_json_text(raw_text_1)

        err_1 = None
        parsed_1 = None
        try:
            parsed_1 = json.loads(cleaned_text_1)
            if not isinstance(parsed_1, dict):
                raise ValueError(f"Output is not a JSON object (got {type(parsed_1).__name__})")
            if model_cls:
                model_cls.model_validate(parsed_1)
            if schema.get("workflow_version") != 2:
                _semantic_sanity_check(stage_name, parsed_1, full_prompt)
        except Exception as e:
            err_1 = str(e)

        log_entry["attempt_1"] = {
            "raw": raw_text_1,
            "cleaned": cleaned_text_1,
            "parsed": parsed_1,
            "error": err_1,
            "input_tokens": in_tok_1,
            "output_tokens": out_tok_1,
            "stop_reason": stop_reason_1,
        }

        if err_1 is None and parsed_1 is not None:
            log_entry["final_status"] = "PASSED_FIRST_TIME"
            self.stage_logs.append(log_entry)
            return parsed_1

        if err_1 and "Semantic sanity check failed" in err_1:
            log_entry["final_status"] = "FAILED_SANITY_CHECK"
            log_entry["error"] = err_1
            self.stage_logs.append(log_entry)
            raise ValueError(err_1)

        # Attempt 2: Corrective Retry
        logger.warning(f"Stage '{stage_name}' attempt 1 failed: {err_1}. Retrying with corrective prompt...")
        corrective_prompt = (
            f"{full_prompt}\n\n"
            f"CRITICAL FIX REQUIRED: Your previous response failed validation with error:\n{err_1}\n\n"
            f"Previous raw response was:\n{raw_text_1}\n\n"
            "You MUST output strictly raw, valid, non-empty JSON matching the required schema with no markdown fences, prose, commentary, or extra fields."
        )

        raw_text_2, in_tok_2, out_tok_2, stop_reason_2 = self._invoke_bedrock_api(corrective_prompt, max_tokens=max_tokens)

        # Explicit truncation detection on retry
        if stop_reason_2 == "max_tokens":
            err_2 = f"Bedrock response truncated on retry for stage '{stage_name}' (stop_reason='max_tokens', output_tokens={out_tok_2}, max_tokens={max_tokens}). Token ceiling hit before complete JSON output."
            log_entry["attempt_2"] = {
                "raw": raw_text_2,
                "cleaned": raw_text_2,
                "parsed": None,
                "error": err_2,
                "input_tokens": in_tok_2,
                "output_tokens": out_tok_2,
                "stop_reason": stop_reason_2,
            }
            log_entry["final_status"] = "TRUNCATED_ON_RETRY"
            log_entry["error"] = err_2
            self.stage_logs.append(log_entry)
            raise ValueError(err_2)

        cleaned_text_2 = _clean_json_text(raw_text_2)

        err_2 = None
        parsed_2 = None
        try:
            parsed_2 = json.loads(cleaned_text_2)
            if not isinstance(parsed_2, dict):
                raise ValueError(f"Retry output is not a JSON object (got {type(parsed_2).__name__})")
            if model_cls:
                model_cls.model_validate(parsed_2)
            if schema.get("workflow_version") != 2:
                _semantic_sanity_check(stage_name, parsed_2, corrective_prompt)
        except Exception as e:
            err_2 = str(e)

        log_entry["attempt_2"] = {
            "raw": raw_text_2,
            "cleaned": cleaned_text_2,
            "parsed": parsed_2,
            "error": err_2,
            "input_tokens": in_tok_2,
            "output_tokens": out_tok_2,
            "stop_reason": stop_reason_2,
        }

        if err_2 is None and parsed_2 is not None:
            log_entry["final_status"] = "PASSED_ON_RETRY"
            self.stage_logs.append(log_entry)
            return parsed_2

        # Outright Failure
        log_entry["final_status"] = "FAILED_OUTRIGHT"
        log_entry["error"] = err_2
        self.stage_logs.append(log_entry)
        raise ValueError(f"Bedrock LLM failed to produce valid JSON for schema stage '{stage_name}': {err_2}")
