# FAIR demo script: Indie Developer track (about 90 seconds)

**Replay only.** No live model request is made. Every scene is a synthetic benchmark case replaying a saved Muse Spark output. Scenes A and B come from Prompt v5 runs. The last scene comes from a Prompt v4 run, and the screen and narration both say so.

**Required label, on screen and spoken:** "Recorded synthetic example — replay, not a live model request."

The Results page shows this as a badge. Also keep it as a caption across the whole video, because the Analyze view does not show the badge. Check the official video requirements before recording: they are not public (see [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md)).

## Setup

From the repository root:
```powershell
cd frontend; npm run build
cd ..\backend; .venv\Scripts\python.exe -m scripts.demo_replay
```
Open `http://127.0.0.1:8010`. Use a window about 1280 px wide at 100% zoom, in light theme. Replay mode loads no key and refuses external connections. It answers only the saved inputs below, exactly as written.

**For the last scene,** stop the server and start it again with the saved earlier-prompt answer. It answers only Scene C:
```powershell
.venv\Scripts\python.exe -m scripts.demo_replay --earlier-prompt-catch
```

## Shot by shot

Cut the typing and paging in editing. Do not change anything shown on screen.

| Time | Screen action | Expected on screen | English narration |
|---|---|---|---|
| 0:00–0:05 | Show Scene A already pasted on the Analyze view | "Free for 21 days" in the terms. The belief in its own field. Status "Replay mode, not live" | "Recorded synthetic example — replay, not a live model request." |
| 0:05–0:11 | Hold, then click **Reveal the Gap** | Replay badge. **Contradiction** | "21 free days. I believe I can cancel after the trial and avoid all fees. The terms contradict me." |
| 0:11–0:20 | Scroll to **The clause that conflicts with your belief** | My belief beside the clause. 239.88 USD, 0.00 USD, At least 19.99 USD | "Here is the clause, beside my belief. And here is what each choice costs. Code calculated these amounts, not the AI." |
| 0:20–0:34 | Hold on the three choices | Same | "One clause separates 240 dollars from nothing, and only if I cancel in time. FAIR won't promise that cancelling is free." |
| 0:34–0:44 | Click **Miss the deadline, then cancel** | The verified, assumed and not settled columns update | "FAIR separates what the terms verify, what it assumes, and what they leave open." |
| 0:44–0:54 | Scroll to **What FAIR checked in this answer** | "did not change the model's answer". Passages checked. Counts for verified, assumed and unknown | "FAIR shows the checks it ran on this answer, and how many things it could not verify." |
| 0:54–1:02 | Scroll to **Future Receipt** | The same totals. "Next expected charge". Assumptions listed under each path | "Future Receipt uses the same figures and lists every assumption." |
| 1:02–1:12 | Click **العربية**, then **تعديل المدخلات**. Enter Scene B. Click **اكشف الفجوة** | Right-to-left. Arabic replay badge. **تعارض**. 828.00 SAR | "The same checks work in Arabic, on Arabic terms." |
| 1:12–1:26 | Cut to the second server. In English, enter Scene C. Click **Reveal the Gap**, then scroll to **What FAIR checked** | **Not stated**. The notice says the answer came from prompt v4. **Muse Spark answered:** Matches, labelled as a saved answer from prompt v4. **FAIR shows:** Not settled. "The cited sentence does not make this promise" | "This one matters most. In a saved run on an earlier prompt, the model told me the price would never change. The quote was real, but it made no such promise. FAIR refused to confirm it. Our current prompt now gets this case right itself, and the check stays as a backstop." |
| 1:26–1:30 | Hold on the same view | Same | "On a small synthetic benchmark it scored 15 of 15 on Validation. Real-world accuracy hasn't been measured. This is information, not financial advice." |

## Optional Arabic narration

Have a native Arabic speaker review this before use.

| Time | Narration |
|---|---|
| 0:00 | مثال اصطناعي مسجَّل — إعادة عرض، وليس طلبًا مباشرًا إلى النموذج. |
| 0:05 | 21 يومًا مجانية. وأعتقد أنني أستطيع الإلغاء بعد التجربة وتجنب كل الرسوم. لكن الشروط تخالف ما أعتقده. |
| 0:11 | هذا هو البند، بجانب اعتقادي. وهذه تكلفة كل خيار. حسب الكود هذه المبالغ، لا الذكاء الاصطناعي. |
| 0:20 | بند واحد يفصل بين 240 دولارًا ولا شيء، وبشرط أن ألغي في الوقت المناسب. ولا يعد FAIR بأن الإلغاء مجاني. |
| 0:34 | يفصل FAIR بين ما تثبته الشروط وما يفترضه وما تتركه مفتوحًا. |
| 0:44 | يعرض FAIR الفحوص التي أجراها على هذه الإجابة، وعدد ما لم يستطع التحقق منه. |
| 0:54 | يستخدم الإيصال المستقبلي الأرقام نفسها ويذكر كل افتراض. |
| 1:02 | تعمل الفحوص نفسها بالعربية، على شروط عربية. |
| 1:12 | هذا هو الأهم. في تشغيل محفوظ بإصدار أقدم من التعليمات، قال النموذج إن السعر لن يتغير أبدًا. كان الاقتباس حقيقيًا، لكنه لا يقدّم هذا الوعد، فرفض FAIR تأكيده. ويجيب الإصدار الحالي عن هذه الحالة بشكل صحيح بنفسه، ويبقى الفحص خط دفاع احتياطيًا. |
| 1:26 | حقق 15 من 15 في مجموعة التحقق على معيار اصطناعي صغير، ولم تُقس دقته في الواقع. هذه معلومات، وليست استشارة مالية. |

## Inputs

**Scene A (FAIR-011)**
- Terms: `Free for 21 days. Then USD 19.99 per month, automatically renewed unless cancelled before the trial ends.`
- Belief: `I can cancel after the trial and definitely avoid all fees.`

**Scene B (FAIR-026)**
- Terms: `التجربة مجانية لمدة 21 يومًا. بعدها يتجدد الاشتراك تلقائيًا بمبلغ 69 SAR شهريًا ما لم يتم الإلغاء قبل نهاية التجربة.`
- Belief: `يمكنني الإلغاء بعد انتهاء التجربة دون أي رسوم بالتأكيد.`

**Scene C (FAIR-012, on the second server)**
- Terms: `Introductory month: USD 9.99. From month two: USD 19.99/month. Subscription continues monthly until cancelled.`
- Belief: `The price will never change after month twelve.`

## Screenshots to capture

1. Analyze view with the replay status visible.
2. Scene A verdict with the replay badge.
3. Expectation Mirror with the clause highlighted in the offer text.
4. Decision Reveal on **Miss the deadline, then cancel**.
5. **What FAIR checked** on Scene A.
6. Future Receipt with the assumptions visible.
7. Scene B in Arabic with the Arabic replay badge.
8. Scene C: **Muse Spark answered** beside **FAIR shows**, with the prompt v4 notice in view.

## Do not say

- That FAIR improves decisions, beats a chatbot, or is accurate in the real world. None of these has been measured.
- That cost totals are always complete. See the known limits in [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md).
- That FAIR is safer or better than direct Muse Spark. In the one comparison run, direct Muse Spark did better.
- That FAIR's checks catch every false reassurance. They read wording, and hand-written tests show gaps.
- That FAIR's checks often catch model errors. They changed 1 of 48 saved outputs, and 0 of 30 on the current prompt.
- That the demo shows a withheld total. No saved output contains one, so it is tested but not shown here.
- That cancelling saves a specific amount. The amount is conditional.
- "Live" about anything in this recording.

## Recording checklist

- [ ] The caption is visible for the whole video and the label is spoken at the start.
- [ ] The Results badge is visible in every result shot.
- [ ] No terminal, `.env`, personal tabs or account names on screen.
- [ ] Any figure you state comes from [EVALUATION.md](EVALUATION.md).
- [ ] Recording and upload were approved separately.
