# Browser-assisted recruitment page reading

> Historical implementation plan for the first browser-reading iteration. Subsequent approved changes added optional GLM fallback, faster DNS resolution, title job-code extraction, and a compact preview. Current behavior and setup are documented in README.md and docs/development.md; the results below describe this original iteration.

**Goal:** Read dynamically loaded public job pages without a model service or company-specific API adapters.

**Architecture:** Keep standard HTML/JobPosting extraction as the fast path. When company or role is missing, run an isolated local Chromium reader, collect rendered content and bounded public JSON responses, then extract candidates with evidence. Recognition never saves applications or assumes personal status/dates.

**Tech stack:** Python 3.9+, optional project-local Playwright/Chromium, existing vanilla JavaScript UI.

**Spec:** User-approved conversation: standard reading → local browser fallback → general field extraction → user reviews; no large model.

## Constraints

- Existing records and display layout remain intact; all UI verification uses a temporary database.
- Browser requests use the existing public-IP validation and pinned connections, including redirects/subresources; no imported login state, private targets, service workers or WebSockets.
- Bound runtime, request counts, resource sizes and extraction output. Missing browser dependencies degrade to a useful message.
- Keep installation optional and document the local runtime; never install software implicitly from the app.

## Tasks

- [x] Extend bounded public transport for browser GET/POST resources while preserving old HTML/image behavior. Verify private-target rejection and existing tests.
- [x] Add `browser_reader.py`: subprocess wrapper `read_rendered_page(url) -> dict`, fresh context worker, bounded DOM/JSON capture and timeouts. Verify missing runtime and an actual delayed-render fixture.
- [x] Add `rendered_extraction.py`: `extract_rendered_page(snapshot) -> result`, general JSON and DOM candidates, same-result evidence, reject ambiguous lists, no personal-state inference. Write failing fixtures for dynamic JSON, plain DOM, ambiguous jobs and untrusted strings first.
- [x] Wire fallback into `recognize`, expose job code/batch in existing candidate UI and distinguish loading/dependency/login/extraction failures. Verify fast path avoids Chromium and failures retain useful candidates.
- [x] Connect recognized company icon sources to existing local logo cache only after saving; preserve manual choice. Verify saved company/URL match before using a candidate.
- [x] Document setup, runtime limits and limits of rule extraction. Test XiaoHongShu plus other independently structured public job pages, run regression suite, restart local app and verify through the UI.

## Verification results

- 70 Python tests (including a real Chromium delayed-content fixture) and 20 Node tests passed. JavaScript syntax and whitespace checks passed.
- XiaoHongShu: live browser UI recognized company, Agent role, Beijing/Shanghai, position 22020 and 2027 batch; filling/saving and automatic logo were verified in an isolated database.
- ByteDance: live rendered page and JSON yielded company, role, Shanghai and public code A78444.
- Apple: tested page did not yield complete job content; retained as a documented limitation rather than claiming universal support.
- Optional Playwright/Chromium installed locally and ignored by Git; no model service. Existing user data was not used for UI test writes.
