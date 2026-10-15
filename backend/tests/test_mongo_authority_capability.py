"""Capability persistence against a unique disposable local Mongo database."""
from uuid import uuid4
from backend.tests import test_role_boundary_and_authority_permissions as permissions
from backend.adapters.mongo.database import MongoDatabaseAdapter
from backend.services.authority_review import AuthorityReview
from backend.services.verified_corpus import VerifiedCorpus
from backend.tests.legal_test_support import test_knowledge


class MongoCapabilityTests(permissions.CapabilityHardeningTests):
    def setUp(self):
        name = 'caseseva_test_capability_' + uuid4().hex
        self.db = MongoDatabaseAdapter(name, 'mongodb://127.0.0.1:27017')
        self.addCleanup(lambda: self.db.db.client.drop_database(name))
        self.corpus = VerifiedCorpus(self.db, test_knowledge())
        self.workflow = AuthorityReview(self.corpus)
        self.admin = permissions._make_user(self.db, 'granting-admin', 'admin')
        self.advocate = permissions._make_user(self.db, 'target-advocate', 'advocate', verified=True)
