"""Independent labels for challenge set v2: a blind form, then a record of what people decided.

  python -m evaluation.review package --out <folder>
  python -m evaluation.review quick --out <folder>
  python -m evaluation.review compare <answers A> <answers B> --out <folder>
  python -m evaluation.review finalize --folder <folder> --decisions <adjudication record>

This code never chooses a label. Where reviewers agree, their answer stands. Where they differ, a person
decides in the adjudication record. It reads the inputs only, never the draft labels, so neither the form
nor the final labels can inherit them. Reviewer files are kept unchanged, with their hashes.

The quick form is for the project owner only. Its answers are owner-reviewed, not independently validated,
and this code refuses them as reviewer files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.evidence import verify_quote

from .challenge import V2_INPUTS_PATH, _amount, _stated, file_sha256, load_inputs

TEMPLATE_PATH = Path(__file__).with_name("review_form_template.html")
QUICK_TEMPLATE_PATH = Path(__file__).with_name("quick_review_template.html")
VERDICTS = ("MATCH", "CONTRADICTION", "UNKNOWN")
PERIODS = ("monthly", "yearly", "weekly", "one_time", "unknown")
FIELDS = ("verdict", "recurring_price", "intro_price", "billing_period", "one_time_fees", "total_12_months")
COMPARISON_NAME = "comparison.json"
RECORD_NAME = "adjudication_record.json"
LABELS_NAME = "challenge_v2_gold_REVIEWED.json"


def _fill(template: Path, fields: tuple[str, ...]) -> str:
    cases = [{k: c[k] for k in fields} for c in load_inputs(V2_INPUTS_PATH)]
    embedded = json.dumps(cases, ensure_ascii=False).replace("</", "<\\/")
    return template.read_text(encoding="utf-8").replace("__CASES__", embedded).replace("__INPUTS_SHA256__", file_sha256(V2_INPUTS_PATH))


def build_form() -> str:
    """Only what a reviewer may see: case ID, language, terms and belief."""
    return _fill(TEMPLATE_PATH, ("case_id", "language", "terms", "expectation"))


def build_quick_form() -> str:
    """The owner's one-at-a-time form. The ID is only a key for the saved answers and is not displayed."""
    return _fill(QUICK_TEMPLATE_PATH, ("case_id", "terms", "expectation"))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_review(path: Path) -> dict:
    """A reviewer's file, checked but never altered. Raises ValueError if it cannot be used."""
    review = json.loads(path.read_text(encoding="utf-8-sig"))
    if review.get("review_type") in ("owner_reviewed", "ai_assisted_owner_review"):
        raise ValueError(f"{path.name} is an owner review, not an independent one")
    if review.get("inputs_sha256") != file_sha256(V2_INPUTS_PATH):
        raise ValueError(f"{path.name} was made from different cases")
    if not str(review.get("reviewer_code") or "").strip():
        raise ValueError(f"{path.name} has no reviewer code")
    wanted = {c["case_id"] for c in load_inputs(V2_INPUTS_PATH)}
    if set(review.get("answers", {})) != wanted:
        raise ValueError(f"{path.name} does not hold exactly the expected cases")
    return review


def _value(answer: dict, field: str) -> Any:
    """Comparable form of one answer. Unreadable text stays as text, so it shows up as a disagreement."""
    if field == "verdict":
        return answer.get("verdict") if answer.get("verdict") in VERDICTS else None
    if field == "billing_period":
        return answer.get("billing_period") if answer.get("billing_period") in PERIODS else None
    if field == "total_12_months":
        if answer.get("total_status") == "unsure" or not answer.get("total_status"):
            return "unsure"
        if answer.get("total_status") != "yes":
            return None
        return _money(answer.get("total_amount"))
    if field == "one_time_fees":
        return sorted(_money(f) for f in str(answer.get("one_time_fees") or "").replace("،", ",").split(",") if f.strip())
    return _money(answer.get(field))


def _money(text: Any) -> str | None:
    stated = _stated(str(text).strip()) if text not in (None, "") else None
    if stated is None:
        return None
    amount = _amount(stated)
    return format(amount.normalize(), "f") if amount is not None else str(stated)


def _quotes(case: dict, answer: dict) -> list[str]:
    lines = [q.strip() for q in str(answer.get("quote") or "").splitlines() if q.strip()]
    return [q for q in lines if verify_quote(q, case["terms"]).verified]


def _kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed = sum(a == b for a, b in pairs) / len(pairs)
    expected = sum((sum(a == v for a, _ in pairs) / len(pairs)) * (sum(b == v for _, b in pairs) / len(pairs)) for v in VERDICTS)
    return None if expected == 1 else round((observed - expected) / (1 - expected), 3)


def compare(paths: list[Path], folder: Path) -> dict:
    if (folder / COMPARISON_NAME).exists():
        raise ValueError(f"{folder} already holds a comparison; originals are never overwritten")
    a, b = [load_review(p) for p in paths]
    if a["reviewer_code"] == b["reviewer_code"]:
        raise ValueError("both files carry the same reviewer code")
    originals = folder / "originals"
    originals.mkdir(parents=True)
    kept = []
    for path, review in zip(paths, (a, b)):
        target = originals / f"reviewer_{review['reviewer_code']}.json"
        shutil.copyfile(path, target)
        kept.append({"reviewer_code": review["reviewer_code"], "file": target.name, "sha256": _file_sha256(target)})

    agreed, items, usable = {}, [], []
    for case in load_inputs(V2_INPUTS_PATH):
        cid = case["case_id"]
        answers = (a["answers"][cid], b["answers"][cid])
        values = {f: [_value(x, f) for x in answers] for f in FIELDS}
        agreed[cid] = {f: v[0] for f, v in values.items() if v[0] == v[1]}
        for f, v in values.items():
            if v[0] != v[1] or (f == "verdict" and v[0] is None) or "unsure" in v:
                items.append({"case_id": cid, "field": f, a["reviewer_code"]: v[0], b["reviewer_code"]: v[1], "decision": None, "method": None, "decided_by": None, "reason": None})
        verdicts = values["verdict"]
        if None not in verdicts:
            usable.append(tuple(verdicts))
        quotes = sorted({q for x in answers for q in _quotes(case, x)})
        agreed[cid]["accepted_evidence"] = quotes
        for x, code in zip(answers, (a["reviewer_code"], b["reviewer_code"])):
            given = [q.strip() for q in str(x.get("quote") or "").splitlines() if q.strip()]
            bad = [q for q in given if q not in quotes and q.lower() not in ("none", "لا يوجد")]
            if bad:
                items.append({"case_id": cid, "field": "evidence_not_verbatim", "reviewer": code, "text": bad, "decision": None, "method": None, "decided_by": None, "reason": None})
        if agreed[cid].get("verdict") in ("MATCH", "CONTRADICTION") and not quotes:
            items.append({"case_id": cid, "field": "evidence_missing", "decision": None, "method": None, "decided_by": None, "reason": None})

    report = {
        "inputs_sha256": file_sha256(V2_INPUTS_PATH),
        "reviewers": kept,
        "verdict_agreement": {"same": sum(x == y for x, y in usable), "of": len(usable), "cohen_kappa": _kappa(usable)},
        "field_agreement": {f: sum(f in agreed[c] for c in agreed) for f in FIELDS},
        "disputed_cases": sorted({i["case_id"] for i in items}),
        "agreed": agreed,
    }
    (folder / COMPARISON_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / RECORD_NAME).write_text(json.dumps({"instructions": "A person fills in decision, method (discussion or third_reviewer), decided_by and reason for each item. For evidence items, decision is the exact accepted quote or null.", "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    number = Decimal(str(value))
    return int(number) if number == number.to_integral_value() else float(number)


def finalize(folder: Path, decisions: Path) -> Path:
    report = json.loads((folder / COMPARISON_NAME).read_text(encoding="utf-8"))
    for kept in report["reviewers"]:
        if _file_sha256(folder / "originals" / kept["file"]) != kept["sha256"]:
            raise ValueError(f"{kept['file']} changed after it was saved")
    items = json.loads(decisions.read_text(encoding="utf-8"))["items"]
    open_items = [i for i in items if i["method"] not in ("discussion", "third_reviewer") or not i["decided_by"] or (i["decision"] is None and i["field"] not in ("evidence_not_verbatim", "evidence_missing") and not i["reason"])]
    if open_items:
        raise ValueError(f"{len(open_items)} adjudication item(s) are not decided, for example {open_items[0]['case_id']} {open_items[0]['field']}")

    annotations = []
    for case in load_inputs(V2_INPUTS_PATH):
        cid = case["case_id"]
        final = dict(report["agreed"][cid])
        mine = [i for i in items if i["case_id"] == cid]
        for item in mine:
            if item["field"] in FIELDS:
                final[item["field"]] = item["decision"]
            elif item["decision"]:
                final["accepted_evidence"] = sorted({*final["accepted_evidence"], item["decision"]})
        if final["verdict"] not in VERDICTS:
            raise ValueError(f"{cid} has no valid verdict")
        for quote in final["accepted_evidence"]:
            if not verify_quote(quote, case["terms"]).verified:
                raise ValueError(f"{cid}: an accepted quote is not in the terms")
        annotations.append({
            "case_id": cid,
            "verdict": final["verdict"],
            "contested": any(i["method"] == "third_reviewer" for i in mine),
            "accepted_evidence": final["accepted_evidence"] if final["verdict"] != "UNKNOWN" else [],
            "cost": {
                "recurring_price": _number(final.get("recurring_price")),
                "billing_period": final.get("billing_period") or "unknown",
                "intro_price": _number(final.get("intro_price")),
                "one_time_fees": [_number(f) for f in final.get("one_time_fees") or []],
                "total_12_months": _number(final.get("total_12_months")),
            },
        })
    labels = {
        "status": "Independently reviewed labels. Each reviewer labelled alone from a blind form. The author draft is a separate, unchanged file.",
        "provenance": {
            "independent_review": True,
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "inputs_sha256": report["inputs_sha256"],
            "reviewers": report["reviewers"],
            "adjudication_record_sha256": _file_sha256(decisions),
            "verdict_agreement": report["verdict_agreement"],
            "decided_by_a_person": len(items),
        },
        "annotations": annotations,
    }
    target = folder / LABELS_NAME
    if target.exists():
        raise ValueError(f"{target.name} already exists; final labels are never overwritten")
    target.write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m evaluation.review", description="Independent labels for challenge set v2")
    sub = p.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("package")
    pack.add_argument("--out", required=True)
    quick = sub.add_parser("quick")
    quick.add_argument("--out", required=True)
    comp = sub.add_parser("compare")
    comp.add_argument("answers", nargs=2)
    comp.add_argument("--out", required=True)
    fin = sub.add_parser("finalize")
    fin.add_argument("--folder", required=True)
    fin.add_argument("--decisions", required=True)
    args = p.parse_args(argv)
    try:
        if args.command == "package":
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "review_form.html").write_text(build_form(), encoding="utf-8")
            print(f"Wrote {out / 'review_form.html'}")
        elif args.command == "quick":
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "owner_quick_review.html").write_text(build_quick_form(), encoding="utf-8")
            print(f"Wrote {out / 'owner_quick_review.html'}")
        elif args.command == "compare":
            report = compare([Path(x) for x in args.answers], Path(args.out))
            print(f"Verdicts: {report['verdict_agreement']}. To decide: {report['disputed_cases'] or 'nothing'}.")
        else:
            target = finalize(Path(args.folder), Path(args.decisions))
            print(f"Wrote {target}, SHA-256 {_file_sha256(target)}")
    except ValueError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
