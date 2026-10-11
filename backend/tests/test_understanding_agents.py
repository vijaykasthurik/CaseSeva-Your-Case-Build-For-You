import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from backend.adapters.mock.database import MockDatabaseAdapter
from backend.services.agent_registry import production_registry
from backend.services.orchestrator import MasterLegalOrchestrator, TransientAgentError
from backend.services.case_blackboard import CaseBlackboard
from backend.services.core_workflow import run_core, save_core_answers
from backend.tests.core_test_support import CoreTestModel, core_case


class CoreAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = MockDatabaseAdapter(Path(self.temp.name) / "db.json")
        self.model = CoreTestModel()
        self.adapters = SimpleNamespace(database=self.db, llm=self.model, mode="mock", phase3_test_double=True)
        self.app = SimpleNamespace(state=SimpleNamespace(adapters=self.adapters))
        core_case(self.db)
        self.controller = MasterLegalOrchestrator(self.db, production_registry(self.adapters), capabilities=("core_reasoning",))
        self.store = CaseBlackboard(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def run_all(self):
        run_core(self.app, "c")
        return self.store.read_board("c")

    def test_seven_production_handlers_execute_through_dependencies(self):
        board = self.run_all()
        self.assertEqual(len(board["nodes"]), 7)
        self.assertTrue(all(n["status"] == "COMPLETED" for n in board["nodes"].values()), {k: n["status"] for k, n in board["nodes"].items()})
        self.assertEqual(board["data"]["domain_classification"]["primary_domain"], "CONSUMER")
        self.assertFalse(board["data"]["domain_classification"]["legal_corpus_ready"])
        case = self.db.get("cases", "c")
        self.assertEqual(case["status"], "CASE_UNDERSTANDING_READY")
        self.assertEqual(case["legal_foundation_status"], "PENDING")
        self.assertNotIn("case_file", case)
        self.assertEqual(set(board["data"]["facts"]), {"F001"})
        self.assertEqual(set(board["data"]["incidents"]), {"I001"})
        self.assertEqual(set(board["data"]["timeline"]), {"T001"})

    def test_repeat_worker_is_idempotent(self):
        self.run_all()
        calls = list(self.model.calls)
        self.run_all()
        self.assertEqual(self.model.calls, calls)

    def test_all_six_domains_uncertain_and_secondary_structures(self):
        for domain in ("CONSUMER", "LABOUR_EMPLOYMENT", "PROPERTY_TENANCY", "CRIMINAL_POLICE", "CIVIL_CONTRACT", "RTI_ADMINISTRATIVE", "OTHER_OR_UNCERTAIN"):
            self.model.domain = domain
            self.store.append_change("c", {"human.DOMAIN_ROUTER": [{"response": "ANSWER", "value": "Classification clarification", "source_id": "answer", "topic": domain}]}, actor="u", reason="domain clarification")
            board = self.run_all()
            self.assertEqual(board["data"]["domain_classification"]["primary_domain"], domain)
        self.model.overrides["DOMAIN_ROUTER"] = {"primary_domain": "PROPERTY_TENANCY", "secondary_domains": ["RTI_ADMINISTRATIVE"]}
        self.store.append_change("c", {"human.DOMAIN_ROUTER": []}, actor="u", reason="new material")
        self.assertEqual(self.run_all()["data"]["domain_classification"]["secondary_domains"], ["RTI_ADMINISTRATIVE"])

    def test_invalid_source_name_evidence_and_domain_fail_closed(self):
        invalid = {
            "PARTY_RELATIONSHIP": lambda o, c: {**o, "parties": [{**o["parties"][0], "name": "Invented Manufacturer"}]},
            "EVIDENCE_MAPPING": {"links": [{"evidence_id": "E999", "fact_id": "F001", "relation": "SUPPORTS", "sources": [{"passage": 0, "excerpt": "Kavya"}]}]},
            "DOMAIN_ROUTER": {"primary_domain": "FAKE_DOMAIN"},
        }
        for name, override in invalid.items():
            self.model.overrides = {name: override}
            self.store.append_change("c", {"human." + name: [{"response": "UNKNOWN", "source_id": name, "topic": name}]}, actor="u", reason="invalid-output test")
            board = self.run_all()
            self.assertEqual(board["nodes"][name]["status"], "FAILED")
            self.assertEqual(board["nodes"]["FACT_TIMELINE"]["status"], "COMPLETED")
            self.model.overrides = {}
            self.store.append_change("c", {"human." + name: []}, actor="u", reason="provider fixed")
            self.run_all()

    def test_language_capability_review_does_not_fabricate_facts(self):
        self.model.overrides["FACT_TIMELINE"] = {"language": {"detected_languages": ["und"], "supported": False, "review_reason": "unsupported"}}
        board = self.run_all()
        self.assertEqual(board["nodes"]["FACT_TIMELINE"]["status"], "REVIEW_REQUIRED")
        self.assertFalse(board["data"]["facts"])

    def test_fact_ids_survive_rerun_and_advocate_value_is_protected(self):
        board = self.run_all()
        self.store.apply_human_override("c", "facts.F001.proposition", "Advocate reviewed wording", actor="advocate", reason="source reviewed")
        self.store.append_change("c", {"human.FACT_TIMELINE": [{"response": "ANSWER", "value": "Updated visit detail", "source_id": "answer", "topic": "visit"}]}, actor="u", reason="new detail")
        board = self.run_all()
        self.assertEqual(board["nodes"]["FACT_TIMELINE"]["status"], "CONFLICT_FOUND")
        self.assertEqual(board["data"]["facts"]["F001"]["proposition"], "Advocate reviewed wording")

    def test_clarification_answer_resumes_only_affected_work(self):
        def questions(output, context):
            if context["prior_answers"]:
                return output
            return {**output, "questions": [{"topic": "relationship_detail", "question": "Was this purchase for personal use?", "priority": "HIGH", "essential": True,
                "response_kind": "DETAIL", "need": "IDENTIFY_EVENT", "fact_ids": ["F001"], "affected": ["DOMAIN_ROUTER"], "material_reason": "Classify the transaction"}]}
        self.model.overrides["CLARIFICATION"] = questions
        self.run_all()
        case = self.db.get("cases", "c")
        self.assertEqual(case["status"], "AWAITING_CLIENT_INFO")
        batch = case["clarification_rounds"][-1]
        calls = {name: self.model.calls.count(name) for name in self.model.calls}
        save_core_answers(self.db, case, batch, [{"question_id": batch["questions"][0]["question_id"], "response": "ANSWER", "value": "Personal use", "evidence_ids": []}], "u")
        board = self.run_all()
        self.assertEqual(board["nodes"]["DOMAIN_ROUTER"]["status"], "COMPLETED")
        self.assertEqual(self.model.calls.count("FACT_TIMELINE"), calls["FACT_TIMELINE"])
        self.assertEqual(self.model.calls.count("PARTY_RELATIONSHIP"), calls["PARTY_RELATIONSHIP"])

    def test_mock_runtime_does_not_use_test_double_automatically(self):
        self.adapters.phase3_test_double = False
        board = self.run_all()
        self.assertEqual(board["nodes"]["FACT_TIMELINE"]["status"], "BLOCKED")
        self.assertEqual(self.model.calls, [])

    def test_same_paragraph_distinct_facts_keep_incident_references(self):
        def facts(output, context):
            first = output['facts'][0]
            output['facts'].append({**first, 'key': 'second_claim', 'proposition': 'The product stopped cooling'})
            output['incidents'][0]['fact_keys'].append('second_claim')
            return output
        self.model.overrides['FACT_TIMELINE'] = facts
        board = self.run_all()
        self.assertEqual(len(board['data']['facts']), 2)
        self.assertEqual(board['data']['incidents']['I001']['fact_ids'], ['F001', 'F002'])

    def test_partial_provider_failure_explicit_retry_preserves_completed_nodes(self):
        def unavailable(output, context):
            raise RuntimeError('PRIVATE_PROVIDER_CONFIG')
        self.model.overrides['PARTY_RELATIONSHIP'] = unavailable
        self.run_all()
        self.assertEqual(self.db.get('cases', 'c')['status'], 'REVIEW_REQUIRED')
        self.assertNotIn('PRIVATE_PROVIDER_CONFIG', str(self.db.get('cases', 'c')['processing_error']))
        fact_calls = self.model.calls.count('FACT_TIMELINE')
        self.model.overrides = {}
        self.db.update('cases', 'c', {'core_retry_requested': True})
        board = self.run_all()
        self.assertEqual(board['nodes']['DOMAIN_ROUTER']['status'], 'COMPLETED')
        self.assertEqual(self.model.calls.count('FACT_TIMELINE'), fact_calls)

    def test_sync_failure_prevents_all_core_calls(self):
        with patch('backend.services.core_workflow.synchronized_raw', side_effect=RuntimeError('PRIVATE_S3_CONFIG')), self.assertLogs('backend.services.core_workflow', level='ERROR'):
            run_core(self.app, 'c')
        self.assertEqual(self.model.calls, [])
        self.assertNotIn('PRIVATE_S3_CONFIG', str(self.db.get('cases', 'c')['processing_error']))

    def test_document_without_available_declaration_cannot_pause(self):
        self.model.overrides['CLARIFICATION'] = {'questions': [{'topic': 'receipt', 'question': 'Upload receipt', 'priority': 'HIGH', 'essential': True,
            'need': 'DOCUMENT', 'response_kind': 'DOCUMENT', 'declaration_index': 99, 'fact_ids': ['F001'], 'affected': ['EVIDENCE_MAPPING'], 'material_reason': 'support'}]}
        board = self.run_all()
        self.assertEqual(board['nodes']['CLARIFICATION']['status'], 'COMPLETED')
        self.assertEqual(board['data']['clarification']['suppressed_requests'][0]['reason'], 'NO_AVAILABLE_DOCUMENT_DECLARATION')

    def test_unknown_answer_suppresses_reworded_same_need(self):
        def questions(output, context):
            return {**output, 'questions': [{'topic': 'renamed' if context['prior_answers'] else 'relationship', 'question': 'What relationship?', 'priority': 'HIGH', 'essential': True,
                'need': 'IDENTIFY_PARTY', 'response_kind': 'DETAIL', 'fact_ids': ['F001'], 'affected': ['DOMAIN_ROUTER'], 'material_reason': 'relationship unclear'}]}
        self.model.overrides['CLARIFICATION'] = questions
        self.run_all()
        case = self.db.get('cases', 'c')
        batch = case['clarification_rounds'][-1]
        save_core_answers(self.db, case, batch, [{'question_id': batch['questions'][0]['question_id'], 'response': 'UNKNOWN', 'value': '', 'evidence_ids': []}], 'u')
        self.assertEqual(self.run_all()['nodes']['CLARIFICATION']['status'], 'COMPLETED')

    def test_source_conflict_preserves_claims_and_resumes_after_human_decision(self):
        def facts(output, context):
            output['facts'].append({**output['facts'][0], 'key': 'disputed', 'certainty': 'CONFLICTED'})
            return output
        self.model.overrides['FACT_TIMELINE'] = facts
        self.model.overrides['RECONCILIATION'] = {'conflicts': [{'fact_ids': ['F001', 'F002'], 'field': 'payment', 'explanation': 'Fixture conflicting claims'}]}
        board = self.run_all()
        self.assertEqual(board['nodes']['RECONCILIATION']['status'], 'CONFLICT_FOUND')
        self.assertEqual(len(board['data']['facts']), 2)
        cid = next(iter(board['conflicts']))
        self.store.resolve_conflict('c', cid, 'KEEP', actor='advocate', reason='Originals reviewed')
        board = self.run_all()
        self.assertEqual(board['nodes']['RECONCILIATION']['status'], 'COMPLETED')
        self.assertEqual(len(board['data']['facts']), 2)

    def test_duplicate_worker_delivery_cannot_call_provider(self):
        import time
        self.db.create('core_workers', {'id': 'c', 'token': 'other-worker', 'lease_until': time.time() + 900})
        run_core(self.app, 'c')
        self.assertEqual(self.model.calls, [])

    def test_persisted_output_rejects_law_and_invalid_identity(self):
        from backend.models.understanding_outputs import VALIDATORS
        board = self.run_all()
        with self.assertRaises(ValueError):
            VALIDATORS['domain_classification']({**board['data']['domain_classification'], 'verified_law': 'invented'})
        changed = copy.deepcopy(board['data']['facts'])
        changed['F001']['fact_id'] = 'F999'
        with self.assertRaises(ValueError):
            VALIDATORS['facts'](changed)
