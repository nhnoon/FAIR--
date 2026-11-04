# Submission checklist

Tick only what you have actually seen pass. Run commands from the repository root unless noted.

**Deadline, from the official event page:** Nov 4, 2026, 9:00 PM ET. The page says dates may change. A third-party listing gives an hour earlier, so work to the earlier time.

## A. Official requirements

Checked on 2026-11-01 against the public [event page](https://dev.meta.ai/events/global-hackathon) and [Cerebral Valley listing](https://cerebralvalley.ai/e/meta-ai-developer-hackathon). The Official Rules are not public. **Do not assume anything marked as needing portal access.**

| Item | Status |
|---|---|
| Submission deadline | CONFIRMED on the event page; exact cut-off to confirm in the portal |
| Tracks: Indie or Startup; each project enters one | CONFIRMED |
| Indie track: individual builders and students, judged on creativity, technical ambition and whether it works | CONFIRMED |
| Which track FAIR enters | **Indie Developer, chosen** |
| Excluded countries and people | CONFIRMED on the event page; whether you qualify is yours to confirm |
| FAIR's application was accepted | REQUIRES PORTAL ACCESS |
| Team size | REQUIRES PORTAL ACCESS |
| Required models or API use | UNVERIFIED: the page lists Meta models as available and states no requirement |
| Repository access or source release | REQUIRES PORTAL ACCESS |
| License | REQUIRES PORTAL ACCESS; **pending, none chosen** |
| Live demo URL | REQUIRES PORTAL ACCESS |
| Video length, format and hosting | REQUIRES PORTAL ACCESS |
| Submission form fields and artifacts | REQUIRES PORTAL ACCESS |
| Intellectual property and privacy terms | REQUIRES PORTAL ACCESS |

Questions for the participant portal or organizers:
1. Where are the Official Rules that participants accepted? Is my application shown as accepted, on the Indie Developer track?
2. What is the exact submission cut-off, including time zone? The event page says Nov 4, 9:00 PM ET.
3. Does the "government-affiliated individuals" exclusion apply to students or staff of public universities?
4. May an Indie entry have more than one person?
5. Must the project use a specific Meta model or the Meta Model API?
6. Must the repository be public, or is private access for judges accepted? If private, who needs access?
7. Is a license required? If so, are any licenses required or excluded?
8. Is a live deployed URL required, or are a repository and a video enough?
9. What are the video's maximum length, format and hosting requirements? Is a clearly labelled replay of saved model outputs acceptable?
10. What fields and files does the submission form require?
11. Who owns the submission, what rights do Meta and Cerebral Valley receive, and what are the privacy obligations?

- [ ] Read the Official Rules and answer these questions. Leave each decision open until then.

## B. Local checks
- [ ] `cd backend; .venv\Scripts\python.exe -m pytest`: all pass
- [ ] `cd frontend; npm test`: all pass
- [ ] `cd frontend; npm run build`: succeeds
- [ ] `backend\.venv\Scripts\python.exe tools\check_release.py`: "No findings"

## C. Live Meta integration
- [x] Live connection verified; the key stays in the git-ignored `backend/.env`
- [x] Development run on Prompt v5: 15/15 on synthetic cases, built on these cases
- [x] Validation run on frozen Prompt v5: 15/15, Arabic 10/10, sharing templates with Development
- [x] One analysis in the real UI shows **Live analysis** with verified quotes (2026-11-03, 23.2 s, CONTRADICTION)
- [x] Comparison in `docs/COMPARISON_PROTOCOL.md`, against author-draft labels: direct Muse Spark did better (2026-11-02)
- [ ] Optional: a single Test run, the only mixed-language measurement (paid; needs approval)
- [ ] Any number quoted publicly comes from `docs/EVALUATION.md`

## D. Repository (each step needs your approval)
- [ ] Choose a license once the Official Rules are known. Add `LICENSE`, then update the README's License section.
- [ ] Use a GitHub no-reply address for commits.
- [ ] Choose private or public repository, once the rules are known.
- [ ] Keep raw run folders out of the release. `docs/EVALUATION.md` records their hashes.
- [ ] Publish only the files in `release-files.txt`. Run `tools/check_release.py` first; it must say "No findings". Never use `git add .` or `git add -A`.
- [x] Local copy of the run folders outside the repository, hashes verified. It is on the same disk.
- [ ] Copy the run folders to a second device. Until then, a disk failure loses the raw evidence.

## E. Deployment (needs approval; see docs/DEPLOYMENT.md)
- [ ] Confirm from the rules whether a live URL is required.
- [ ] Decide the public settings: live calls on or off, `RATE_LIMIT_PER_MINUTE`, `DAILY_ANALYSIS_LIMIT`.
- [ ] Backend deployed; `/api/health` returns 200.
- [ ] Frontend deployed with `VITE_API_BASE_URL`; backend `CORS_ORIGINS` set to the frontend origin.
- [ ] One live analysis works on the deployed URL (paid).

## F. Submission materials
- [ ] Demo video following `docs/DEMO_SCRIPT.md`: scenarios stated as synthetic, replays labelled as replays.
- [ ] Project description from `docs/PROJECT_DESCRIPTION.md`, English and Arabic.
- [ ] A native Arabic speaker has reviewed the UI and sample outputs.
- [ ] Links ready, as the rules require.
- [ ] Submit several hours before the deadline.
