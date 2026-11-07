"""Live smoke tests against a Didit sandbox application.

They run only with ``DIDIT_SANDBOX_API_KEY`` set (``uv run pytest -m live``), never in
the default CI, and create nothing that costs money beyond sandbox sessions.
"""

from __future__ import annotations

import os

import pytest

import didit

API_KEY = os.environ.get("DIDIT_SANDBOX_API_KEY")
WORKFLOW_ID = os.environ.get("DIDIT_SANDBOX_WORKFLOW_ID")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not API_KEY, reason="DIDIT_SANDBOX_API_KEY is not set"),
]


@pytest.fixture
def client() -> didit.Didit:
    return didit.Didit(api_key=API_KEY, base_url=os.environ.get("DIDIT_SANDBOX_BASE_URL"))


def test_list_workflows(client: didit.Didit) -> None:
    page = client.workflows.list(limit=5)
    assert page.count is None or page.count >= 0


def test_list_sessions_first_page(client: didit.Didit) -> None:
    page = client.sessions.list(limit=2)
    assert len(page.results) <= 2


@pytest.mark.skipif(not WORKFLOW_ID, reason="DIDIT_SANDBOX_WORKFLOW_ID is not set")
def test_create_session_and_read_decision(client: didit.Didit) -> None:
    assert WORKFLOW_ID is not None
    session = client.sessions.create(workflow_id=WORKFLOW_ID, vendor_data="sdk-python-smoke")
    assert session.url
    decision = client.sessions.retrieve_decision(session.session_id)
    assert decision.session_id == session.session_id


def test_unknown_session_is_not_found(client: didit.Didit) -> None:
    with pytest.raises(didit.NotFoundError):
        client.sessions.retrieve_decision("00000000-0000-4000-8000-000000000000")
