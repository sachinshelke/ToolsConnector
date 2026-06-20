"""Pydantic models for the LinkedIn Lead Sync connector.

LinkedIn's Lead Sync API splits a lead into two documents that you have to
join yourself:

- A **Lead Gen Form** (``/rest/leadForms``) defines the *questions* — each
  carries a ``predefinedField`` (``EMAIL``, ``PHONE_NUMBER``, ``FIRST_NAME``,
  …) that gives it meaning, keyed by an integer ``questionId``.
- A **Lead Form Response** (``/rest/leadFormResponses``) is what a member
  *submitted*. Its answers reference questions **only by ``questionId``** —
  the raw email/phone *value* is there, but unlabeled.

So an answer of ``"ada@example.com"`` is meaningless until you map its
``questionId`` to the form's ``EMAIL`` field. :meth:`LeadForm.question_map`
and the connector's ``list_leads`` resolution do exactly that.

Models use ``extra="ignore"`` so unmodeled vendor fields are dropped rather
than raising, matching the rest of the connector suite.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class LeadFormQuestion(BaseModel):
    """One question in a Lead Gen Form.

    ``predefined_field`` is the load-bearing field for lead resolution: it is
    LinkedIn's canonical field name (``EMAIL``, ``WORK_EMAIL``,
    ``PHONE_NUMBER``, ``FIRST_NAME``, ``LAST_NAME``, ``COMPANY_NAME``,
    ``JOB_TITLE``, …). Empty for fully custom questions, where ``name`` /
    ``label`` carry the author's wording instead.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    question_id: int
    name: str = ""
    predefined_field: str = ""
    label: str = ""  # human-readable, flattened from the question's localized text
    required: bool = False
    # For multiple-choice questions: option id → option label. Lets the lead
    # resolver turn a selected option id (e.g. 3) into its text (e.g. "11-50").
    options: dict[int, str] = Field(default_factory=dict)


class LeadForm(BaseModel):
    """A LinkedIn Lead Gen Form definition (the question template)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    name: str = ""
    owner: dict[str, Any] = Field(default_factory=dict)  # {"organization"|"sponsoredAccount": urn}
    state: str = ""  # DRAFT | PUBLISHED | ARCHIVED
    version_id: int = 0
    created: Optional[int] = None  # epoch ms
    last_modified: Optional[int] = None  # epoch ms
    questions: list[LeadFormQuestion] = Field(default_factory=list)
    hidden_fields: list[dict[str, Any]] = Field(default_factory=list)
    privacy_policy_url: str = ""

    def question_map(self) -> dict[int, LeadFormQuestion]:
        """Index questions by ``question_id`` for joining against answers."""
        return {q.question_id: q for q in self.questions}


class LeadAnswer(BaseModel):
    """A single answer within a lead's form response.

    Exactly one of ``text`` (free-text / predefined fields like email/phone)
    or ``options`` (multiple-choice selected option ids) is populated.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    question_id: int
    name: str = ""  # LinkedIn echoes the question name on each answer (default-returned)
    text: Optional[str] = None
    options: list[int] = Field(default_factory=list)


class LeadResponse(BaseModel):
    """A submitted lead — what a member entered into a Lead Gen Form.

    ``answers`` carries the raw values keyed by ``question_id``. ``fields`` is
    the *resolved* view (LinkedIn field name → value, e.g.
    ``{"EMAIL": "ada@example.com", "PHONE_NUMBER": "+1..."}``) and is only
    populated by the connector's ``list_leads`` / ``get_lead`` actions, which
    fetch the owning form and perform the join. ``list_lead_responses`` (the
    raw finder) leaves it empty.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    id: str
    owner: dict[str, Any] = Field(default_factory=dict)
    submitter: str = ""  # urn:li:person:... — the member who submitted the lead
    versioned_form_urn: str = ""  # urn:li:versionedLeadGenForm:(urn:li:leadGenForm:N,V)
    lead_type: str = ""  # SPONSORED | COMPANY | EVENT | ORGANIZATION_PRODUCT
    test_lead: bool = False
    submitted_at: Optional[int] = None  # epoch ms
    campaign: Optional[str] = None  # urn:li:sponsoredCampaign:... (sponsored leads)
    answers: list[LeadAnswer] = Field(default_factory=list)
    consent_responses: list[dict[str, Any]] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)

    def text_answers(self) -> dict[int, str]:
        """``question_id`` → text value, for joining against a form's questions."""
        return {a.question_id: a.text for a in self.answers if a.text is not None}
