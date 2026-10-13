"""Loopback review API using existing application accounts; never provisions roles."""
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def create_app(identity_path, authority_path):
    from fastapi import FastAPI
    from backend.adapters.mock.database import MockDatabaseAdapter
    from backend.adapters.mock.auth import MockAuthAdapter
    from backend.routes.auth import router as auth
    from backend.routes.authorities import router as authorities
    for path in (identity_path, authority_path):
        if not Path(path).is_file():
            raise ValueError('An existing local database file is required; no database is created')
    identity = MockDatabaseAdapter(identity_path)
    if not any(u.get('role') == 'admin' and u.get('password_hash') for u in identity.list('users')):
        raise ValueError('No existing password-authenticated administrator in the selected application database; provisioning is not supported by this command')
    app = FastAPI(title='CaseSeva isolated authority review')
    app.state.adapters = SimpleNamespace(database=MockDatabaseAdapter(authority_path), auth=MockAuthAdapter(identity, seed_demo=False))
    app.state.authority_identity_database = identity
    # Normal login/session verification only; no signup or account/role mutations.
    for route in auth.routes:
        if route.path in {'/api/auth/login', '/api/auth/logout', '/api/auth/me'}:
            app.router.routes.append(route)
    app.include_router(authorities)
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--identity-database', type=Path, required=True)
    parser.add_argument('--authority-database', type=Path, default=ROOT / '.localdev/phase4-authority-review/database.json')
    parser.add_argument('--port', type=int, default=8012)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.identity_database, args.authority_database), host='127.0.0.1', port=args.port, access_log=False)
