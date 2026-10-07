"""Zero-shot invoice detection with Laya (convaiinnovations/laya).

Laya answers typed questions about a "state" (here: an email) in one forward pass. It is not a
generative model: each answer option gets a [MASK] marker and the head scores the markers.
The model files are loaded from a local folder using the loader shipped in the Hub repo
(``rl_agent_api.py`` + ``rl_common.py``), so no network access is needed at run time.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from .data import EmailItem

logger = logging.getLogger(__name__)

DEFAULT_LAYA_DIR = Path(__file__).resolve().parent.parent / "models" / "laya"

# Each question set maps to: the Laya question, and which answer key means "invoice".
# Several phrasings are evaluated because zero-shot results are sensitive to wording.
QUESTIONS: dict[str, dict[str, Any]] = {
    # Two-option choice with neutral keys: the Laya README recommends this over `noul` on the
    # English checkpoint, whose true/false labels can dominate the answer.
    "invoice_ab": {
        "question": {"type": "choice",
                     "instructions": "Is the email in `body` sending an invoice, i.e. a bill asking the recipient to pay?",
                     "criteria": {"A": "yes, the email sends an invoice or bill for payment",
                                  "B": "no, the email is about something else"}},
        "positive": "A",
    },
    "invoice_noul": {
        "question": {"type": "noul", "instructions": "Is this email sending an invoice that the recipient has to pay?"},
        "positive": "true",
    },
    "doc_type": {
        "question": {"type": "choice",
                     "instructions": "What kind of document does the email in `body` send or discuss?",
                     "criteria": {"invoice": "a bill requesting payment for goods or services",
                                  "receipt": "proof of a payment that was already made",
                                  "purchase_order": "an order placed with a supplier",
                                  "quotation": "a price quote or estimate",
                                  "statement": "a bank statement, payslip, remittance or payment advice",
                                  "other": "any other document"}},
        "positive": "invoice",
    },
}


class LayaZeroShot:
    def __init__(self, model_dir: Path | str = DEFAULT_LAYA_DIR, device: str | None = None,
                 question_ids: list[str] | None = None, clean_body: bool = True,
                 include_attachment_name: bool = False) -> None:
        self.model_dir = Path(model_dir).resolve()
        if not (self.model_dir / "model.safetensors").is_file():
            raise FileNotFoundError(f"Laya weights not found in {self.model_dir}")
        if str(self.model_dir) not in sys.path:
            sys.path.insert(0, str(self.model_dir))  # rl_agent_api imports rl_common by name
        from email_utils import clean_email_body  # type: ignore[import-not-found]
        from rl_agent_api import RLAgent  # type: ignore[import-not-found]

        self._clean = clean_email_body
        self.agent = RLAgent(str(self.model_dir), device=device)
        self.question_ids = question_ids or list(QUESTIONS)
        unknown = set(self.question_ids) - set(QUESTIONS)
        if unknown:
            raise ValueError(f"Unknown question ids: {sorted(unknown)}")
        self.clean_body = clean_body
        self.include_attachment_name = include_attachment_name
        logger.info("Laya loaded from %s on %s; questions=%s", self.model_dir, self.agent.device, self.question_ids)

    def build_state(self, email: EmailItem, mode: str) -> dict[str, str]:
        """mode='body': body only. mode='header_body': sender, recipient, subject and body.

        The attachment file name is left out by default: in this generated data it encodes the
        label (e.g. ``lookalike_payslip_045.pdf``), which would make the test meaningless.
        """
        body = self._clean(email.body) if self.clean_body else email.body
        if mode == "body":
            return {"body": body}
        if mode != "header_body":
            raise ValueError(f"Unknown mode {mode!r}")
        h = email.headers
        state = {"from": h.get("From", ""), "to": h.get("To", ""), "subject": h.get("Subject", ""), "body": body}
        if self.include_attachment_name and h.get("X-Attachment-Name"):
            state["attachment"] = h["X-Attachment-Name"]
        return state

    def predict(self, email: EmailItem, mode: str) -> dict[str, dict[str, Any]]:
        """Return {question_id: {"p_invoice": float, "answer": str}} for one email (one forward pass)."""
        questions = {qid: QUESTIONS[qid]["question"] for qid in self.question_ids}
        res = self.agent.system_one(self.build_state(email, mode), questions)["answers"]
        out: dict[str, dict[str, Any]] = {}
        for qid in self.question_ids:
            ans, pos = res[qid], QUESTIONS[qid]["positive"]
            if ans["type"] == "noul":
                p = float(ans["noul"])
                out[qid] = {"p_invoice": p, "answer": "true" if p >= 0.5 else "false"}
            else:
                out[qid] = {"p_invoice": float(ans["probabilities"][pos]), "answer": ans["choice"]}
        return out
