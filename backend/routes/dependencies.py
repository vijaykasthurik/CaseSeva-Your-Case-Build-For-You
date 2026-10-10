from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = request.app.state.adapters.auth.get_current_user(credentials.credentials)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def get_case_or_error(request: Request, case_id: str, user: dict) -> dict:
    case = request.app.state.adapters.database.get("cases", case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if case["owner_user_id"] != user["id"]:
        if case.get("origin") == "ADVOCATE_WALK_IN" and user.get("role") == "advocate" and user.get("id") == case.get("created_by_advocate_id"):
            from ..services.sharing import require_access
            require_access(request, case_id, user, "case_file")
        else:
            raise HTTPException(status_code=403, detail="You do not have access to this case")
    return case
