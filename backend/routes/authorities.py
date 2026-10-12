"""Admin-only source review. Reviewer identity and time never come from a form."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from .dependencies import get_current_user
from .advocates import require_admin
from ..models.understanding import Strict
from ..models.legal_foundation import LegalSource
from ..services.verified_corpus import VerifiedCorpus
from ..services.authority_review import AuthorityReview

router = APIRouter(prefix='/api/admin/authorities')


def workflow(request, user):
    require_admin(request, user)
    return AuthorityReview(VerifiedCorpus(request.app.state.adapters.database))


class ReviewDecision(Strict):
    expected_version: str
    decision: Literal['REVIEWED_PRIMARY', 'REJECTED', 'STALE']
    note: str = Field(min_length=1, max_length=4000)


@router.get('')
def pending(request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    return {'sources': service.corpus.sources(), 'readiness': service.corpus.readiness(),
            'nationwide_coverage': 'NOT_READY'}


@router.post('')
def submit(body: LegalSource, request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    try:
        return service.submit(body.model_dump(), actor=user['id'])
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post('/{source_id}/review')
def review(source_id: str, body: ReviewDecision, request: Request, user=Depends(get_current_user)):
    service = workflow(request, user)
    try:
        return service.decide(source_id, body.expected_version, reviewer=user, decision=body.decision, note=body.note)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
