import hashlib
import hmac
import secrets
from typing import Any
from uuid import uuid4

from ..auth import AuthAdapter
from ..database import DatabaseAdapter


class MockAuthAdapter(AuthAdapter):
    def __init__(self, database: DatabaseAdapter, seed_demo: bool = True):
        self.database = database
        if seed_demo and not any(user.get("email") == "demo.advocate@caseseva.local" for user in database.list("users")):
            database.create("users", {
                "id": "seed-verified-advocate",
                "full_name": "Meena Raman",
                "email": "demo.advocate@caseseva.local",
                "mobile_number": "9000000001",
                "preferred_language": "English",
                "state": "Tamil Nadu",
                "district_city": "Chennai",
                "role": "advocate",
                "password_hash": self._hash_password("DemoPassword123"),
                "bar_council": "Tamil Nadu and Puducherry Bar Council",
                "enrolment_number": "TN/DEMO/2015",
                "enrolment_year": 2015,
                "place_of_practice": "Chennai",
                "court_region": "Madras High Court",
                "practice_domains": ["Consumer"],
                "languages": ["English", "Tamil"],
                "verification_status": "VERIFIED",
            })
            database.create("users", {
                "id": "seed-pending-advocate",
                "full_name": "Pending Advocate",
                "email": "pending.advocate@caseseva.local",
                "mobile_number": "9000000002",
                "preferred_language": "English",
                "state": "Tamil Nadu",
                "district_city": "Coimbatore",
                "role": "advocate",
                "password_hash": self._hash_password("DemoPassword123"),
                "bar_council": "Tamil Nadu and Puducherry Bar Council",
                "enrolment_number": "TN/PENDING/2020",
                "enrolment_year": 2020,
                "place_of_practice": "Coimbatore",
                "court_region": "Coimbatore",
                "practice_domains": ["Consumer"],
                "languages": ["English", "Tamil"],
                "verification_status": "VERIFICATION_PENDING",
            })

    @staticmethod
    def validate_credentials(email: str, password: str) -> str:
        normalized = email.strip().lower()
        if not normalized or len(password) < 8:
            raise ValueError("Email is required and password must be at least 8 characters")
        return normalized

    def provision_local_review_admin(self, email: str, password: str, *, allow_bootstrap: bool, operator: str) -> dict[str, Any]:
        """Local review bootstrap only. Not exposed by signup or any HTTP route."""
        import re
        from .database import MockDatabaseAdapter
        from ...models.case import utc_now
        from ..mongo.database import MongoDatabaseAdapter
        if not allow_bootstrap or not isinstance(self.database, (MockDatabaseAdapter, MongoDatabaseAdapter)):
            raise ValueError("Explicit local review bootstrap authorization required")
        normalized = self.validate_credentials(email, password)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid administrator email")
        now = utc_now()
        user = {'id': uuid4().hex, 'email': normalized, 'full_name': 'Authority review administrator',
                'role': 'admin', 'password_hash': self._hash_password(password), 'created_at': now,
                'provisioning': {'method': 'LOCAL_INTERACTIVE_REVIEW_BOOTSTRAP',
                    'scope': 'PHASE4_REVIEW_ONLY', 'local_operator': operator, 'created_at': now}}
        self.database.create_local_review_admin(user)
        return self._public_user(user)

    @staticmethod
    def _hash_password(password: str, salt: str | None = None) -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return f"{salt}${digest}"

    def provision_additional_review_admin(self, email: str, password: str, *, session_token: str,
                                         allow_onboarding: bool, operator: str) -> dict[str, Any]:
        """Authenticated local onboarding; never bootstrap, promotion or human-review approval."""
        import re
        from .database import MockDatabaseAdapter
        from ...models.case import utc_now
        from ..mongo.database import MongoDatabaseAdapter
        if not allow_onboarding or not isinstance(self.database, (MockDatabaseAdapter, MongoDatabaseAdapter)):
            raise ValueError('Explicit local reviewer onboarding authorization required')
        authorizer = self.get_current_user(session_token)
        if not authorizer or authorizer.get('role') != 'admin':
            raise ValueError('An authenticated existing administrator is required')
        normalized = self.validate_credentials(email, password)
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', normalized):
            raise ValueError('Enter a valid new reviewer email')
        if normalized == authorizer['email'].strip().lower():
            raise ValueError('The new reviewer must use a different email')
        now = utc_now()
        user = {'id': uuid4().hex, 'email': normalized, 'full_name': 'Authority review administrator',
                'role': 'admin', 'password_hash': self._hash_password(password), 'created_at': now,
                'provisioning': {'method': 'AUTHENTICATED_LOCAL_REVIEW_ONBOARDING',
                    'scope': 'PHASE4_REVIEW_ONLY', 'authorized_by': authorizer['id'],
                    'local_operator': operator, 'created_at': now, 'human_independence_verified': False}}
        self.database.create_additional_review_admin(user, session_token=session_token)
        return self._public_user(user)

    def signup(self, profile: dict[str, Any], password: str) -> dict[str, Any]:
        normalized = self.validate_credentials(profile["email"], password)
        if any(user["email"] == normalized for user in self.database.list("users")):
            raise ValueError("User already exists")
        user = {
            "id": uuid4().hex,
            "full_name": profile["full_name"].strip(),
            "email": normalized,
            "mobile_number": profile["mobile_number"].strip(),
            "preferred_language": profile["preferred_language"].strip(),
            "state": profile["state"].strip(),
            "district_city": profile["district_city"].strip(),
            "role": profile.get("role", "client"),
            "password_hash": self._hash_password(password),
        }
        if user["role"] == "advocate":
            user.update({
                "bar_council": profile.get("bar_council"),
                "enrolment_number": profile.get("enrolment_number"),
                "enrolment_year": profile.get("enrolment_year"),
                "place_of_practice": profile.get("place_of_practice"),
                "court_region": profile.get("court_region"),
                "practice_domains": profile.get("practice_domains", []),
                "languages": profile.get("languages", []),
                "verification_status": "VERIFICATION_PENDING",
            })
        self.database.create("users", user)
        return self._issue_session(user)

    def login(self, email: str, password: str) -> dict[str, Any]:
        normalized = email.strip().lower()
        users = self.database.list("users")
        user = next((item for item in users if item["email"] == normalized), None)
        if user is None:
            raise ValueError("Invalid credentials")
        salt, expected = user["password_hash"].split("$", 1)
        actual = self._hash_password(password, salt).split("$", 1)[1]
        if not hmac.compare_digest(actual, expected):
            raise ValueError("Invalid credentials")
        return self._issue_session(user)

    def _issue_session(self, user: dict[str, Any]) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        self.database.create("sessions", {"id": token, "user_id": user["id"]})
        return {"session_token": token, "user": self._public_user(user)}

    @staticmethod
    def _public_user(user: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in user.items() if key != "password_hash"}

    def logout(self, token: str) -> None:
        if token:
            self.database.delete("sessions", token)

    def verify_session(self, token: str) -> bool:
        return bool(token and self.database.get("sessions", token))

    def get_current_user(self, token: str) -> dict[str, Any] | None:
        session = self.database.get("sessions", token)
        if not session:
            return None
        user = self.database.get("users", session["user_id"])
        return self._public_user(user) if user else None

    def update_profile(self, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        user = self.database.update("users", user_id, changes)
        return self._public_user(user)
