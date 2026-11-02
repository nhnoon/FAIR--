# FAIR demo script: Indie Developer track (about 90 seconds)

**Replay only.** No live model request is made. Every scene is a synthetic benchmark case replaying a saved Muse Spark output from a Prompt v5 run.

**Required label, on screen and spoken:** "Recorded synthetic example — replay, not a live model request."

The Results page shows this as a badge. Also keep it as a caption across the whole video, because the Analyze view does not show the badge. Check the official video requirements before recording: they are not public (see [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md)).

## Setup

From the repository root:
```powershell
cd frontend; npm run build
cd ..\backend; .venv\Scripts\python.exe -m scripts.demo_replay
```
Open `http://127.0.0.1:8010`. Use a window about 1280 px wide at 100% zoom, in light theme. Replay mode loads no key and refuses external connections. It answers only the three inputs below, exactly as written.

## Shot by shot

Cut the typing and paging in editing. Do not change anything shown on screen.

| Time | Screen action | Expected on screen | English narration |
|---|---|---|---|
| 0:00–0:08 | Show the Analyze view | Status "Replay mode, not live" | "Recorded synthetic example — replay, not a live model request." |
| 0:08–0:18 | Paste Scene A terms and belief | "Free for 21 days" in the terms. The belief in its own field | "The offer promises 21 free days. I believe I can cancel after the trial and definitely avoid all fees." |
| 0:18–0:28 | Click **Reveal the Gap** | Replay badge. **Contradiction** | "Muse Spark judged my belief against the terms. FAIR then checked its answer." |
| 0:28–0:40 | Scroll to **Expectation Mirror**. Click **Show in source text** | Claim 1, **Contradicted**. The clause is highlighted in the offer text | "Each claim gets its own verdict, linked to the exact clause. Every quote is checked word for word." |
| 0:40–0:54 | Scroll to **Your belief, and what each choice costs**. Click **Miss the deadline, then cancel** | 239.88 USD, 0.00 USD, At least 19.99 USD. The verified, assumed and not settled columns update | "Decision Reveal shows what each choice costs. Code calculated these amounts, not the AI, and it keeps verified facts apart from assumptions." |
| 0:54–1:06 | Scroll to **Future Receipt** | The same totals. "Next expected charge". Assumptions listed under each path | "Future Receipt uses the same figures and lists every assumption. FAIR won't promise that cancelling is free." |
| 1:06–1:18 | Click **العربية**, then **تعديل المدخلات**. Enter Scene B. Click **اكشف الفجوة** | Right-to-left. Replay badge in Arabic. **تعارض**. 828.00 SAR | "The same checks work in Arabic, on Arabic terms." |
| 1:18–1:30 | Click **English**, then **Edit inputs**. Enter Scene C. Click **Reveal the Gap** | **Not stated**. Claim: "The price will never change after month 12." | "And when the terms don't settle something, FAIR refuses to confirm it. On a small synthetic benchmark, it scored 15 of 15 on Validation, but real-world accuracy hasn't been measured. This is information, not financial advice." |

## Optional Arabic narration

Have a native Arabic speaker review this before use.

| Time | Narration |
|---|---|
| 0:00 | مثال اصطناعي مسجَّل — إعادة عرض، وليس طلبًا مباشرًا إلى النموذج. |
| 0:08 | يعد العرض بـ21 يومًا مجانية. وأعتقد أنني أستطيع الإلغاء بعد التجربة وتجنب كل الرسوم بالتأكيد. |
| 0:18 | حكم Muse Spark على اعتقادي مقابل الشروط، ثم تحقق FAIR من إجابته. |
| 0:28 | لكل ادعاء حكمه الخاص، مرتبطًا بالبند نفسه. ويُفحص كل اقتباس كلمةً بكلمة. |
| 0:40 | يعرض كشف القرار تكلفة كل خيار. حسب الكود هذه المبالغ، لا الذكاء الاصطناعي، وهو يفصل الحقائق المُتحقق منها عن الافتراضات. |
| 0:54 | يستخدم الإيصال المستقبلي الأرقام نفسها ويذكر كل افتراض. ولا يعد FAIR بأن الإلغاء مجاني. |
| 1:06 | تعمل الفحوص نفسها بالعربية، على شروط عربية. |
| 1:18 | وعندما لا تحسم الشروط أمرًا، يرفض FAIR تأكيده. حقق 15 من 15 في مجموعة التحقق على معيار اصطناعي صغير، لكن دقته في الواقع لم تُقس. هذه معلومات، وليست استشارة مالية. |

## Inputs

**Scene A (FAIR-011)**
- Terms: `Free for 21 days. Then USD 19.99 per month, automatically renewed unless cancelled before the trial ends.`
- Belief: `I can cancel after the trial and definitely avoid all fees.`

**Scene B (FAIR-026)**
- Terms: `التجربة مجانية لمدة 21 يومًا. بعدها يتجدد الاشتراك تلقائيًا بمبلغ 69 SAR شهريًا ما لم يتم الإلغاء قبل نهاية التجربة.`
- Belief: `يمكنني الإلغاء بعد انتهاء التجربة دون أي رسوم بالتأكيد.`

**Scene C (FAIR-012)**
- Terms: `Introductory month: USD 9.99. From month two: USD 19.99/month. Subscription continues monthly until cancelled.`
- Belief: `The price will never change after month twelve.`

## Screenshots to capture

1. Analyze view with the replay status visible.
2. Scene A verdict with the replay badge.
3. Expectation Mirror with the clause highlighted in the offer text.
4. Decision Reveal on **Miss the deadline, then cancel**.
5. Future Receipt with the assumptions visible.
6. Scene B in Arabic with the Arabic replay badge.
7. Scene C **Not stated** verdict.

## Do not say

- That FAIR improves decisions, beats a chatbot, or is accurate in the real world. None of these has been measured.
- That cost totals are always complete. See the known limits in [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md).
- That the demo shows a withheld total. No saved output contains one, so it is tested but not shown here.
- That cancelling saves a specific amount. The amount is conditional.
- "Live" about anything in this recording.

## Recording checklist

- [ ] The caption is visible for the whole video and the label is spoken at the start.
- [ ] The Results badge is visible in every result shot.
- [ ] No terminal, `.env`, personal tabs or account names on screen.
- [ ] Any figure you state comes from [EVALUATION.md](EVALUATION.md).
- [ ] Recording and upload were approved separately.
