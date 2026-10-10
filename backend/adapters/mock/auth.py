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
    def _hash_password(password: str, salt: str | None = None) -> str:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
        return f"{salt}${digest}"

    def signup(self, profile: dict[str, Any], password: str) -> dict[str, Any]:
        normalized = profile["email"].strip().lower()
        if not normalized or len(password) < 8:
            raise ValueError("Email is required and password must be at least 8 characters")
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
