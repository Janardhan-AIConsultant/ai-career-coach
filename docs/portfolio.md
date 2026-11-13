# Career Achievement Portfolio (Phase 11)

Registered users. Public viewing needs no login.

## What it is
A **derived** record of verified learning on the platform. Items are rebuilt from real records and cannot be typed in:

| Item kind | Source (must still qualify) | Evidence level |
|---|---|---|
| `learning_path` | Completed roadmap (>= 80% of required activities and all assessments passed) | `learned` |
| `assessment` | Best passing attempt per assessment | `assessed` |
| `certificate` | Valid (not revoked) platform certificate | by type: learning = `learned`, assessment = `assessed`, project = `demonstrated` |
| `project` | Passed project evaluation | `demonstrated` ("practically demonstrated") |

**Skill evidence:** every skill collects the items that mention it and reports each level reached plus the highest (`learned` < `assessed` < `demonstrated`). A skill is only "demonstrated" through a passed project (or that project's certificate).
**No fabrication:** there is no endpoint to add or edit an item, title, level or skill (`PATCH /items/{id}` only toggles visibility; unknown fields are ignored). Items vanish automatically when their evidence does (certificate revoked, project or roadmap deleted). Every output (API, PDF, LinkedIn text, resume section) states that this is learning evidence, **not professional employment experience**, that certificates are platform-issued and not externally accredited, and that project reviews are automated static reviews (code not executed).
**Automatic updates:** passing an assessment, completing or deleting a roadmap, issuing/revoking a certificate, and evaluating/deleting a project all refresh the portfolio (if the user has one) in the same transaction; `GET /portfolio` also re-syncs.

## Endpoints (`/api/v1/portfolio`)
| Endpoint | Purpose |
|---|---|
| `GET /` | Owner view: settings, achievement timeline (newest first), skill evidence, stats (plans, activities, study hours, assessments, certificates, projects) |
| `PUT /settings` | Visibility, public display name, headline, summary, per-section visibility |
| `PATCH /items/{id}` | Show/hide one item |
| `POST /rotate-slug` | New public URL; the old one stops working |
| `GET /public/{slug}` | **Public** read-only view (rate limited) |
| `GET /linkedin-summary` | LinkedIn-ready "About" text (<= 2,600 chars) + certification entries (name, issuer, date, credential ID and URL) |
| `POST /resume-integration`, `GET /resume-section` | Approve/withdraw, then get a "Learning and certifications" resume block |
| `POST /report` | PDF or DOCX export (stored as a report; download via `/reports/{id}/download`) |

## Privacy and consent
- **Private by default.** Publishing requires `consent_public: true` and a display name the owner chooses (markup and control characters stripped); consent time and publish/unpublish events are audit-logged.
- The public URL is `FRONTEND_URL/portfolio/<slug>` with a random 10-character slug; **withdrawing consent makes it 404 immediately**. Private, withdrawn, deleted and unknown portfolios return an identical 404.
- Selective visibility: hide any item, or any section (`summary`, `timeline`, `skills`, `learning_paths`, `assessments`, `certificates`, `projects`, `scores`). Public skills are computed only from items that are shown.
- The public view contains no email, user id or internal ids. Project items show the repository URL only if the project is visible.
- **Resume integration only after explicit approval:** `GET /resume-section` returns 409 until approved; it only returns text for you to paste (nothing is merged into a resume automatically) and honours hidden items.
- Deleting the account deletes the portfolio and its public page.

## Limits
- The public page is JSON; the React page that renders it comes with the frontend work.
- "Learning activities" are summarised as counts and study hours, not listed individually.
- Skill names come from the platform taxonomy and assessment/project definitions; they are not free text.
- Migration `0007` is verified on SQLite and rendered offline for PostgreSQL only.
