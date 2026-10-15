import json
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from .dependencies import get_current_user
from .advocates import require_admin
from ..models.understanding import Strict
from ..models.legal_foundation import LegalSource
from ..services.verified_corpus import VerifiedCorpus
from ..services.authority_review import AuthorityReview, is_authorized_authority_reviewer

router = APIRouter(prefix='/api/admin/authorities')

QUEUE_PATH = Path("docs/audits/phase4_review_queue.json")
MANIFEST_PATH = Path("docs/audits/phase4_review_session_manifest.json")
PACKET_DIR = Path("docs/audits/review_packets")


def require_authority_reviewer(user: dict):
    if not is_authorized_authority_reviewer(user):
        if user.get("role") == "admin":
            raise HTTPException(403, "Platform administrators are not legal reviewers; a verified advocate with LEGAL_AUTHORITY_REVIEW capability is required.")
        if user.get("role") != "advocate":
            raise HTTPException(403, "A verified advocate with LEGAL_AUTHORITY_REVIEW capability is required.")
        if user.get("verification_status") != "VERIFIED":
            raise HTTPException(403, "Advocate verification is required for legal authority review.")
        raise HTTPException(403, "Explicit LEGAL_AUTHORITY_REVIEW capability required.")


def require_admin_or_reviewer(request: Request, user: dict):
    if user.get("role") == "admin":
        require_admin(request, user)
        return
    if is_authorized_authority_reviewer(user):
        return
    raise HTTPException(403, "Administrator or authorized legal authority reviewer access required.")


def workflow(request, user):
    require_admin_or_reviewer(request, user)
    return AuthorityReview(VerifiedCorpus(request.app.state.adapters.database),
        accounts_db=getattr(request.app.state, 'authority_identity_database', None))


@router.get('/review-queue')
def get_review_queue(request: Request, user=Depends(get_current_user)):
    require_authority_reviewer(user)
    if not QUEUE_PATH.exists():
        raise HTTPException(404, "Review queue not found")
    try:
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"Failed to load review queue: {exc}")


@router.get('/session-manifest')
def get_session_manifest(request: Request, user=Depends(get_current_user)):
    require_authority_reviewer(user)
    if not MANIFEST_PATH.exists():
        raise HTTPException(404, "Session manifest not found")
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"Failed to load session manifest: {exc}")


@router.get('/review-packets/{source_id}')
def get_review_packet(source_id: str, request: Request, user=Depends(get_current_user)):
    require_authority_reviewer(user)
    packet_file = PACKET_DIR / f"{source_id}.json"
    if not packet_file.exists():
        raise HTTPException(404, f"Review packet for {source_id} not found")
    try:
        return json.loads(packet_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(500, f"Failed to load review packet: {exc}")


class ReviewDecision(Strict):
    expected_version: str
    decision: Literal['REVIEWED_PRIMARY', 'REJECTED', 'STALE', 'NEEDS_NEW_REVISION']
    note: str = Field(min_length=1, max_length=4000)


@router.get('')
def pending(request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    return {'sources': service.corpus.sources(), 'readiness': service.corpus.readiness(),
            'nationwide_coverage': 'NOT_READY'}


@router.post('')
def submit(body: LegalSource, request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    if body.model_fields_set & {'reviewed_by', 'reviewed_at', 'review_id', 'revision_status', 'parent_revision', 'revision_request_id'}:
        raise HTTPException(422, 'Reviewer identity, time and revision lineage are server-owned')
    try:
        return service.submit(body.model_dump(), actor=user['id'])
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get('/{source_id}/history')
def history(source_id: str, request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    current = service.corpus.get(source_id)
    if not current:
        raise HTTPException(404, 'Authority not found')
    return {'current_revision': current['version_id'],
        'versions': [v for v in service.db.list('legal_authority_versions') if v['source']['source_id'] == source_id],
        'reviews': [r for r in service.db.list('legal_authority_reviews') if r['source_id'] == source_id],
        'submissions': [s for s in service.db.list('legal_review_submissions') if s['source_id'] == source_id]}


@router.post('/{source_id}/review')
def review(source_id: str, body: ReviewDecision, request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    try:
        return service.decide(source_id, body.expected_version, reviewer=user, decision=body.decision, note=body.note)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
