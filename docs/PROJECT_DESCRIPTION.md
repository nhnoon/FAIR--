# FAIR (تَبَيَّن): project description

## Short version (Indie Developer track)

FAIR checks what you believe about a subscription offer against what its terms say, in Arabic or English. Meta's Muse Spark judges each claim in your belief and quotes the terms. FAIR's code then rejects any quote that is not word for word in the offer, and calculates costs from verified values only. If the terms do not settle a claim, FAIR says so instead of reassuring you. If it cannot total the cost reliably, it withholds the total and explains why. On a small synthetic benchmark, a frozen prompt scored 15/15 on Validation, but real-world accuracy has not been measured.

## Submission message

**One sentence.** FAIR checks what you believe about a subscription against the exact words of its terms, in Arabic or English, and shows you the clause, the cost of each choice, and everything it could not verify.

**30-second pitch.** "You sign up for a free trial believing you can cancel and owe nothing. One clause says otherwise, and you find out on your bank statement. FAIR starts from what you believe, not from a summary. Muse Spark tests your belief against the terms. Then FAIR's code tests Muse Spark: every quote has to be in the offer, a word like "never" needs a sentence that actually makes that promise, and only code does the money. When FAIR can't verify something, it says so, in Arabic or English."

**Why Muse Spark matters here.** The hard part is language: deciding whether a sentence supports, contradicts or simply does not address a belief written in someone's own words, across Arabic and English. Quote matching and arithmetic can be done by code, and in FAIR they are. Judgment is what the model is for.

**What FAIR proves.**
- A model's reading can be held to a checkable standard: a quote that must exist, and money that only code calculates.
- In a saved Prompt v4 run, the model answered MATCH on "the price will never change". FAIR's check changed that to not settled. This is one real case, and the current prompt now gets it right itself.
- On a small synthetic benchmark, frozen Prompt v5 scored 15/15 on Validation, including 10/10 in Arabic.

**What FAIR does not claim.**
- That it beats using Muse Spark directly. In the one comparison run, on 12 synthetic cases with author-draft labels, direct Muse Spark did better (verdicts 11/12 against 9/12).
- Real-world accuracy, or better decisions. Neither has been measured.
- That its checks often catch errors. They changed 1 of 48 saved outputs, and 0 of 30 on the current prompt.
- That its checks catch every false reassurance. They read wording, so a confident wrong answer citing a real price sentence can still pass, as hand-written tests show.
- That its cost totals are always complete. See the known limits below.

**Why Indie Developer track.** Judging looks at creativity, technical ambition and whether it works.
- **Creativity:** it tests your belief instead of summarizing the terms, then shows what each choice costs.
- **Technical ambition:** a bilingual verification layer over the model's output, with exact-decimal costs that withhold a total rather than guess.
- **Whether it works:** a real interface in English and Arabic, with saved model outputs anyone can replay, plus automated and browser tests.

## Technical architecture

1. **Reading (Meta Model API, `muse-spark-1.3`).** One request per analysis, using one versioned prompt. The model returns claims, verdicts, quotes and extracted terms as JSON. It does no arithmetic.
2. **Verification (Python).** Output is treated as untrusted: schema check, word-for-word quote matching with character offsets, promise and topic checks, and price, currency and billing-period checks. What fails is excluded or shown as not settled.
3. **Calculation (Python `Decimal`).** Only verified values reach the cost engine. It produces the 1, 3 and 12 month totals used by both Decision Reveal and Future Receipt.
4. **Completeness.** Wording checks withhold a total, or label it conditional, when the terms state something the verified prices leave out, such as unknown seat counts, tax or percentage fees. FAIR never calculates a percentage.
5. **Audit view.** Each result shows what the checks did to that answer: the model's verdict against the one displayed, how many passages passed, and counts of what is verified, assumed and unknown.
6. **Interface (React, English and Arabic).** Every finding is marked as from the terms, AI interpretation, calculated, assumption or unknown. The API key stays on the server.

## Known financial limits

Cost totals are not universally complete, because the checks read wording.
- A percentage increase phrased unusually ("your bill goes up by 15%") is not recognized.
- A percentage or amount written in words can be missed.
- A required fee worded with "if" can stay outside a total. The total is labelled conditional and the fee is named.
- Some valid offers listing several plans have their total withheld, which is safe but over-cautious.
- Conflicting billing statements are not detected. If an offer says both monthly and annual, FAIR can show the timing of whichever one the model cites.

## English

**FAIR checks what you believe about a subscription offer against what its terms actually say, in Arabic or English.**

**The problem.** Fine print rarely fools people about everything. It leaves them holding one wrong belief: "I can cancel after the trial and avoid all fees." A summary of the terms does not test that belief, and the mistake only shows up on a bank statement.

**What FAIR does.** You paste the terms and write what you believe. Meta's Muse Spark splits your belief into separate claims and judges each one against the terms: supported, contradicted, or not settled. FAIR then treats that answer as untrusted. Code checks that every quote exists word for word, that a promise like "never" is actually made, and that a price is stated as money, in that currency, for that billing period. If a claim fails, FAIR says it is not settled rather than reassuring you.

**Decision Twin.** When the terms contradict you, FAIR puts your belief beside the sentence that conflicts with it, then shows what each choice costs: keep paying, cancel before the deadline, or miss it. Each choice separates what is verified, what is assumed, and what the terms leave open. The amounts come from a deterministic engine, never from the model, and cancelling is always shown as conditional.

**Why Muse Spark.** Deciding whether a sentence supports, contradicts or simply does not address a belief written in someone's own words takes language understanding across Arabic and English. That is Muse Spark's job in FAIR. Quote checks and arithmetic stay in code.

**What was measured.** On a small synthetic benchmark, Prompt v5 scored 15/15 on Development and, once frozen, 15/15 on Validation, including 10/10 in Arabic, with all 36 cost totals correct and no false MATCH on those 15 cases.

**What is unproven.** Those cases are short and synthetic, the two sets share templates, the labels are author drafts, and Validation was not fully independent of development. Real-world accuracy is unmeasured. No user study shows better decisions. In a 12-case comparison scored against author-draft labels, direct Muse Spark did better than FAIR on verdicts, prices and totals. Mixed-language quality has been tried on only 3 cases.

**Built with.** Meta Model API (`muse-spark-1.3`), FastAPI, Pydantic, React, Vite, Tailwind CSS, Pytest, Vitest.

## العربية

**يقارن FAIR ما تعتقده عن عرض اشتراك بما تنص عليه شروطه فعلًا، بالعربية أو الإنجليزية.**

**المشكلة.** نادرًا ما تضلل الشروط الدقيقة الناس في كل شيء، لكنها تترك لديهم اعتقادًا خاطئًا واحدًا، مثل: «يمكنني الإلغاء بعد انتهاء التجربة دون أي رسوم». ملخص الشروط لا يختبر هذا الاعتقاد، ولا يظهر الخطأ إلا في كشف الحساب البنكي.

**ماذا يفعل FAIR.** تلصق الشروط وتكتب ما تعتقده. يقسّم نموذج Muse Spark من Meta اعتقادك إلى ادعاءات منفصلة، ويحكم على كل منها مقابل الشروط: متوافق، أو متعارض، أو غير محسوم. ثم يتعامل FAIR مع هذه الإجابة على أنها غير موثوقة: تتحقق الشيفرة من وجود كل اقتباس حرفيًا في النص، ومن أن وعدًا مثل «أبدًا» مذكور فعلًا، ومن أن السعر مذكور بصفته مبلغًا بتلك العملة ولتلك الدورة. وإذا لم يجتز الادعاء هذه الفحوص، يقول FAIR إنه غير محسوم بدلًا من طمأنتك.

**التوأم القراري (Decision Twin).** عندما تتعارض الشروط مع اعتقادك، يضع FAIR اعتقادك بجانب الجملة التي تعارضه، ثم يعرض تكلفة كل خيار: مواصلة الدفع، أو الإلغاء قبل الموعد النهائي، أو فوات الموعد. ويفصل كل خيار بين ما هو مُتحقق منه وما هو مفترض وما تتركه الشروط مفتوحًا. تأتي المبالغ من محرك حساب حتمي وليس من النموذج، ويُعرض الإلغاء دائمًا على أنه مشروط.

**لماذا Muse Spark.** يتطلب الحكم على جملة، هل تدعم اعتقادًا مكتوبًا بكلمات صاحبه أم تعارضه أم لا تتناوله أصلًا، فهمًا للغة بالعربية والإنجليزية. هذه مهمة Muse Spark في FAIR، أما فحص الاقتباسات والحساب فيبقيان في الشيفرة.

**ما جرى قياسه.** على مجموعة اختبار اصطناعية صغيرة، حقق الإصدار الخامس من التعليمات 15 من 15 في مجموعة التطوير، ثم بعد تجميده 15 من 15 في مجموعة التحقق، منها 10 من 10 بالعربية، مع صحة جميع إجماليات التكلفة الـ36 ودون أي تطابق خاطئ في تلك الحالات الـ15.

**ما لم يثبت بعد.** هذه الحالات قصيرة واصطناعية، وتشترك المجموعتان في قوالب واحدة، والتصنيفات مسودات من إعداد المؤلف، ولم تكن مجموعة التحقق مستقلة تمامًا عن قرارات التطوير. لم تُقَس الدقة في العالم الحقيقي، ولا توجد دراسة مستخدمين تثبت تحسّن القرارات. ولم يُقارَن FAIR باستخدام Muse Spark مباشرة، ولم تُقَس الجودة في النصوص المختلطة اللغة. أُعدّ بروتوكول للمقارنة لكنه لم يُنفَّذ بعد.

**التقنيات.** Meta Model API (`muse-spark-1.3`)، وFastAPI، وPydantic، وReact، وVite، وTailwind CSS، وPytest، وVitest.
