import unittest
from unittest.mock import patch
from backend.tests.helpers import test_app, client_account
from backend.services.engine1 import run_engine1
from backend.services.clarification import gate
from backend.routes.clarification import router


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.directory, self.app, self.client = test_app()
        self.app.include_router(router)
        self.user, self.headers = client_account(self.client)
        self.id = self.client.post('/api/cases', headers=self.headers).json()['case']['case_id']
        self.client.patch(f'/api/cases/{self.id}', headers=self.headers, json={'stage': 'NEW_CONSULTATION', 'client_story': 'I need to explain an incident. The date is unknown.'})
        self.question = {'question_id': 'Q1', 'incident_id': 'I1', 'question': 'When did this happen?', 'control': 'date', 'choices': [], 'legal_reason': 'The incident date may affect the applicable law.'}
        original = self.app.state.adapters.llm.generate
        def generate(prompt, schema):
            output = original(prompt, schema)
            if schema['stage'] == 'fact_extraction': output['incidents'] = [{'incident_id': 'I1', 'description': 'User-reported incident', 'fact_ids': ['F001']}]
            if schema['stage'] == 'missing_information': return {'questions': [self.question]}
            return output
        self.app.state.adapters.llm.generate = generate

    def tearDown(self): self.directory.cleanup()

    def test_gate_pauses_before_legal_processing_and_rejects_unanswered_questions(self):
        run_engine1(self.app, self.id)
        case = self.app.state.adapters.database.get('cases', self.id)
        self.assertEqual(case['status'], 'AWAITING_CLIENT_INFO')
        self.assertNotIn('case_file', case)
        self.assertEqual(case['engines']['1']['status'], 'WAITING_FOR_INPUT')
        self.assertEqual(self.client.post(f'/api/cases/{self.id}/clarifications', headers=self.headers, json={'answers': []}).status_code, 422)

    def test_unknown_is_valid_and_reconciliation_does_not_invent_a_date(self):
        run_engine1(self.app, self.id)
        with patch('backend.routes.clarification.dispatch') as dispatch:
            response = self.client.post(f'/api/cases/{self.id}/clarifications', headers=self.headers, json={'answers': [{'question_id': 'Q1', 'response': 'UNKNOWN'}]})
        self.assertEqual(response.status_code, 200, response.text)
        dispatch.assert_called_once_with(self.app, 1, self.id, start_stage='RECONCILIATION')
        run_engine1(self.app, self.id, start_stage='RECONCILIATION')
        case = self.app.state.adapters.database.get('cases', self.id)
        self.assertEqual(case['case_file']['timeline'], [])
        self.assertEqual(case['case_file']['unknown_answers'][0]['response'], 'UNKNOWN')

    def test_gate_stops_after_two_rounds_and_carries_unknowns_for_advocate(self):
        db = self.app.state.adapters.database
        data = {'incidents': [{'incident_id': 'I1'}]}
        for identifier in ('Q1', 'Q2'):
            case = db.get('cases', self.id)
            self.assertTrue(gate(db, case, data, [{**self.question, 'question_id': identifier}], 'RECONCILIATION'))
        self.assertFalse(gate(db, db.get('cases', self.id), data, [{**self.question, 'question_id': 'Q3'}], 'RECONCILIATION'))
        self.assertEqual(data['advocate_flags'][0]['type'], 'clarification_limit')
        self.assertEqual(len(db.get('cases', self.id)['clarification_rounds']), 2)

    def test_another_account_cannot_answer(self):
        run_engine1(self.app, self.id)
        _, other = client_account(self.client, 'other')
        self.assertEqual(self.client.post(f'/api/cases/{self.id}/clarifications', headers=other, json={'answers': [{'question_id': 'Q1', 'response': 'LATER'}]}).status_code, 403)
