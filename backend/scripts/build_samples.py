"""Build the frontend's SAMPLE PREVIEW fixtures.

The "model outputs" below are HAND-WRITTEN SYNTHETIC examples, not produced by
Meta or any AI. They are passed through the real pipeline (evidence verification
+ deterministic cost engine) using an offline fake client, so every highlight,
rejection and cost in the preview comes from the actual backend code.

No network access. Offer texts are original and not taken from FAIR-Bench.

Run from backend/:  .venv\\Scripts\\python.exe -m scripts.build_samples
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.analyzer import analyze
from app.config import Settings
from app.meta_client import MetaClient
from app.schemas import AnalyzeRequest

OUT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "samples" / "samples.json"
SAMPLE_MODEL_LABEL = "sample-fixture (not AI generated)"


class _OfflineSDK:
    def __init__(self, text: str):
        self.responses = SimpleNamespace(create=lambda **_: SimpleNamespace(output_text=text))


def _fact(value, evidence=None):
    return {"value": value, "evidence": evidence}


SAMPLES = [
    {
        "id": "trial-autorenew",
        "title": {"en": "Free trial that turns paid", "ar": "تجربة مجانية تتحول إلى اشتراك مدفوع"},
        "terms": (
            "Premium plan: free for 14 days. After the trial, your plan renews automatically at USD 11.99 "
            "per month unless you cancel at least 24 hours before the trial ends. A one-time activation fee "
            "of USD 2.50 is charged when you sign up."
        ),
        "expectation": "I can try it for free and I won't be charged anything unless I choose to upgrade.",
        "model_output": {
            "extraction": {
                "currency": _fact("USD", "your plan renews automatically at USD 11.99 per month"),
                "trial_days": _fact(14, "free for 14 days."),
                "recurring_price": _fact("11.99", "your plan renews automatically at USD 11.99 per month"),
                "billing_period": _fact("monthly", "your plan renews automatically at USD 11.99 per month"),
                "auto_renewal": _fact("yes", "your plan renews automatically"),
                "cancellation_requirement": _fact(
                    "Cancel at least 24 hours before the trial ends.",
                    "unless you cancel at least 24 hours before the trial ends.",
                ),
                "one_time_fees": [
                    {
                        "label": "activation fee",
                        "amount": "2.50",
                        "evidence": "A one-time activation fee of USD 2.50 is charged when you sign up.",
                    }
                ],
            },
            "verdict": "CONTRADICTION",
            "verdict_evidence": (
                "After the trial, your plan renews automatically at USD 11.99 per month unless you cancel "
                "at least 24 hours before the trial ends."
            ),
            "explanation": {
                "en": (
                    "It does not stay free. After 14 days it renews automatically at USD 11.99 per month unless "
                    "you cancel at least 24 hours before the trial ends, and a USD 2.50 activation fee is charged "
                    "at signup."
                ),
                "ar": (
                    "لا يبقى مجانيًا. بعد 14 يومًا يتجدد تلقائيًا بسعر 11.99 دولار شهريًا ما لم تُلغِ قبل نهاية "
                    "التجربة بـ24 ساعة على الأقل، كما تُدفع رسوم تفعيل قدرها 2.50 دولار عند التسجيل."
                ),
            },
        },
    },
    {
        "id": "intro-price-ar",
        "title": {"en": "Introductory price (Arabic terms)", "ar": "سعر ترويجي (شروط بالعربية)"},
        "terms": (
            "عرض ترحيبي: الشهر الأول بسعر 15 SAR فقط. ابتداءً من الشهر الثاني يصبح السعر 45 SAR شهريًا، "
            "ويتجدد الاشتراك تلقائيًا حتى تقوم بإلغائه. يمكنك الإلغاء في أي وقت من صفحة الحساب."
        ),
        "expectation": "سأدفع 15 ريالًا في الشهر الأول ثم 45 ريالًا كل شهر بعد ذلك.",
        "model_output": {
            "extraction": {
                "currency": _fact("SAR", "الشهر الأول بسعر 15 SAR فقط."),
                "intro_price": _fact("15", "الشهر الأول بسعر 15 SAR فقط."),
                "intro_periods": _fact(None),
                "recurring_price": _fact("45", "ابتداءً من الشهر الثاني يصبح السعر 45 SAR شهريًا"),
                "billing_period": _fact("monthly", "ابتداءً من الشهر الثاني يصبح السعر 45 SAR شهريًا"),
                "auto_renewal": _fact("yes", "ويتجدد الاشتراك تلقائيًا حتى تقوم بإلغائه."),
                "cancellation_requirement": _fact(
                    "الإلغاء متاح في أي وقت من صفحة الحساب.", "يمكنك الإلغاء في أي وقت من صفحة الحساب."
                ),
            },
            "verdict": "MATCH",
            "verdict_evidence": "ابتداءً من الشهر الثاني يصبح السعر 45 SAR شهريًا، ويتجدد الاشتراك تلقائيًا حتى تقوم بإلغائه.",
            "explanation": {
                "en": "Correct: the first month costs 15 SAR, then 45 SAR per month, renewing automatically until you cancel.",
                "ar": "توقعك صحيح: الشهر الأول بـ15 ريالًا، ثم 45 ريالًا شهريًا مع تجديد تلقائي حتى الإلغاء.",
            },
        },
    },
    {
        "id": "missing-details",
        "title": {"en": "Missing renewal details", "ar": "تفاصيل التجديد غير مذكورة"},
        "terms": (
            "Get Pro access for USD 6.99. Renewal and cancellation details are available in your account "
            "settings after purchase."
        ),
        "expectation": "I only pay once and it never renews.",
        "model_output": {
            "extraction": {
                "currency": _fact("USD", "Get Pro access for USD 6.99."),
                "recurring_price": _fact("6.99", "Get Pro access for USD 6.99."),
                "billing_period": _fact("unknown"),
                "auto_renewal": _fact("not_stated"),
            },
            "verdict": "UNKNOWN",
            "verdict_evidence": (
                "Renewal and cancellation details are available in your account settings after purchase."
            ),
            "explanation": {
                "en": "The offer does not say whether this is a one-time payment or whether it renews; those details are only in account settings.",
                "ar": "لا يوضح العرض إن كان الدفع لمرة واحدة أو إن كان يتجدد؛ هذه التفاصيل موجودة فقط في إعدادات الحساب.",
            },
        },
    },
    {
        "id": "evidence-guard",
        "title": {"en": "Evidence guard: unsupported claim", "ar": "حماية الأدلة: ادعاء غير مدعوم"},
        "terms": "Monthly plan: 29 SAR/month, renews automatically. يجب طلب الإلغاء قبل موعد التجديد بـ48 ساعة على الأقل.",
        "expectation": "If I cancel mid-month, I get a refund for the unused days.",
        # Deliberately wrong output: invented quote and invented fee. The validator must catch both.
        "model_output": {
            "extraction": {
                "currency": _fact("SAR", "Monthly plan: 29 SAR/month"),
                "recurring_price": _fact("29", "Monthly plan: 29 SAR/month"),
                "billing_period": _fact("monthly", "Monthly plan: 29 SAR/month"),
                "auto_renewal": _fact("yes", "renews automatically"),
                "cancellation_requirement": _fact(
                    "Cancel at least 48 hours before renewal.", "يجب طلب الإلغاء قبل موعد التجديد بـ48 ساعة على الأقل."
                ),
                "one_time_fees": [
                    {"label": "service fee", "amount": "5", "evidence": "A service fee of 5 SAR applies."}
                ],
            },
            "verdict": "MATCH",
            "verdict_evidence": "Refunds are given for unused days.",
            "explanation": {"en": "You will be refunded for unused days.", "ar": "سيتم استرداد قيمة الأيام غير المستخدمة."},
        },
    },
]


def _claim(text, topic, verdict, evidence, role, en, ar):
    return {"text": text, "topic": topic, "verdict": verdict, "evidence": evidence, "evidence_role": role, "explanation": {"en": en, "ar": ar}}


# Decision Twin additions (prompt v2): structured cancellation rule + atomic claims.
# Still hand-written synthetic model output; the real pipeline judges every claim.
DECISION_TWIN_EXTRAS = {
    "trial-autorenew": {
        "extraction": {
            "cancel_by": _fact("trial_end", "unless you cancel at least 24 hours before the trial ends."),
            "cancel_notice": _fact({"amount": 24, "unit": "hours"}, "unless you cancel at least 24 hours before the trial ends."),
        },
        "claims": [
            _claim("I can try it for free.", "trial", "MATCH", "free for 14 days.", "supports",
                   "The plan is free for the first 14 days.", "الخطة مجانية لأول 14 يومًا."),
            _claim("I won't be charged unless I choose to upgrade.", "renewal", "CONTRADICTION",
                   "After the trial, your plan renews automatically at USD 11.99 per month unless you cancel at least 24 hours before the trial ends.",
                   "contradicts",
                   "You are charged automatically after the trial unless you cancel in time.",
                   "تُحاسَب تلقائيًا بعد التجربة ما لم تُلغِ في الوقت المحدد."),
        ],
    },
    "intro-price-ar": {
        "extraction": {"cancel_by": _fact("anytime", "يمكنك الإلغاء في أي وقت من صفحة الحساب.")},
        "claims": [
            _claim("سأدفع 15 ريالًا في الشهر الأول.", "price", "MATCH", "الشهر الأول بسعر 15 SAR فقط.", "supports",
                   "The first month costs 15 SAR.", "الشهر الأول بسعر 15 ريالًا."),
            _claim("ثم 45 ريالًا كل شهر بعد ذلك.", "price", "MATCH", "ابتداءً من الشهر الثاني يصبح السعر 45 SAR شهريًا", "supports",
                   "From month two the price is 45 SAR per month.", "ابتداءً من الشهر الثاني يصبح السعر 45 ريالًا شهريًا."),
        ],
    },
    "missing-details": {
        "extraction": {"cancel_by": _fact("not_stated")},
        "claims": [
            _claim("I only pay once.", "price", "UNKNOWN",
                   "Renewal and cancellation details are available in your account settings after purchase.", None,
                   "The offer does not say whether the payment is one-time.", "لا يوضح العرض إن كان الدفع لمرة واحدة."),
            _claim("It never renews.", "renewal", "UNKNOWN", None, None,
                   "Renewal rules are not in the offer text.", "قواعد التجديد غير موجودة في نص العرض."),
        ],
    },
    "evidence-guard": {
        "extraction": {
            "cancel_by": _fact("renewal", "يجب طلب الإلغاء قبل موعد التجديد بـ48 ساعة على الأقل."),
            "cancel_notice": _fact({"amount": 48, "unit": "hours"}, "يجب طلب الإلغاء قبل موعد التجديد بـ48 ساعة على الأقل."),
        },
        # Deliberately wrong: cites a REAL sentence that is irrelevant to refunds. The relevance guard must catch it.
        "claims": [
            _claim("If I cancel mid-month, I get a refund for the unused days.", "refund", "MATCH", "renews automatically", "supports",
                   "You will be refunded.", "سيتم استرداد المبلغ."),
        ],
    },
}

for _s in SAMPLES:
    _x = DECISION_TWIN_EXTRAS[_s["id"]]
    _s["model_output"]["extraction"].update(_x["extraction"])
    _s["model_output"]["claims"] = _x["claims"]

_DT_TERMS = (
    "Start with a 7-day free trial. When the trial ends, your subscription renews automatically at USD 9.99 per month "
    "until you cancel. To avoid being charged, cancel at least 48 hours before the trial ends. Payments are non-refundable."
)
SAMPLES.append(
    {
        "id": "decision-twin",
        "title": {"en": "Several beliefs at once", "ar": "عدة توقعات في جملة واحدة"},
        "terms": _DT_TERMS,
        "expectation": "I think the trial is free, it ends automatically, and I can cancel whenever I want.",
        "model_output": {
            "extraction": {
                "currency": _fact("USD", "your subscription renews automatically at USD 9.99 per month until you cancel."),
                "trial_days": _fact(7, "Start with a 7-day free trial."),
                "recurring_price": _fact("9.99", "your subscription renews automatically at USD 9.99 per month until you cancel."),
                "billing_period": _fact("monthly", "your subscription renews automatically at USD 9.99 per month until you cancel."),
                "auto_renewal": _fact("yes", "your subscription renews automatically"),
                "cancellation_requirement": _fact(
                    "Cancel at least 48 hours before the trial ends.", "To avoid being charged, cancel at least 48 hours before the trial ends."
                ),
                "cancel_by": _fact("trial_end", "To avoid being charged, cancel at least 48 hours before the trial ends."),
                "cancel_notice": _fact({"amount": 48, "unit": "hours"}, "To avoid being charged, cancel at least 48 hours before the trial ends."),
            },
            "verdict": "CONTRADICTION",
            "verdict_evidence": "When the trial ends, your subscription renews automatically at USD 9.99 per month until you cancel.",
            "explanation": {
                "en": "The trial is free, but it does not end on its own: it becomes a paid plan at USD 9.99 per month unless you cancel at least 48 hours before it ends.",
                "ar": "التجربة مجانية، لكنها لا تنتهي تلقائيًا: تتحول إلى اشتراك مدفوع بسعر 9.99 دولار شهريًا ما لم تُلغِ قبل انتهائها بـ48 ساعة على الأقل.",
            },
            "claims": [
                _claim("The trial is free.", "trial", "MATCH", "Start with a 7-day free trial.", "supports",
                       "The first 7 days are free.", "الأيام السبعة الأولى مجانية."),
                _claim("The subscription ends automatically.", "renewal", "CONTRADICTION",
                       "When the trial ends, your subscription renews automatically at USD 9.99 per month until you cancel.", "contradicts",
                       "It renews automatically as a paid plan; it does not end by itself.",
                       "يتجدد تلقائيًا كاشتراك مدفوع، ولا ينتهي من تلقاء نفسه."),
                _claim("I can cancel whenever I want.", "cancellation", "UNKNOWN",
                       "To avoid being charged, cancel at least 48 hours before the trial ends.", None,
                       "The terms set a deadline to avoid being charged, but do not say whether you can cancel at any other time.",
                       "تحدد الشروط موعدًا نهائيًا لتجنب الرسوم، لكنها لا تذكر إن كان الإلغاء ممكنًا في أي وقت آخر."),
            ],
        },
    }
)


def build() -> list[dict]:
    settings = Settings(api_key="offline-fixture", live_calls_enabled=True, model=SAMPLE_MODEL_LABEL)
    out = []
    for s in SAMPLES:
        client = MetaClient(settings, sdk_client=_OfflineSDK(json.dumps(s["model_output"], ensure_ascii=False)))
        response = analyze(AnalyzeRequest(terms=s["terms"], expectation=s["expectation"]), client)
        out.append(
            {
                "id": s["id"],
                "title": s["title"],
                "terms": s["terms"],
                "expectation": s["expectation"],
                "response": response.model_dump(mode="json"),
            }
        )
    return out


def render() -> str:
    payload = {
        "_notice": "SAMPLE PREVIEW - NOT AI GENERATED. Hand-written synthetic model outputs, processed by FAIR's real "
        "evidence validator and cost engine. Regenerate with: python -m scripts.build_samples",
        "samples": build(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT_PATH.relative_to(OUT_PATH.parents[3])}")
