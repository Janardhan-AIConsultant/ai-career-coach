# Career Intelligence (Phase 7)

Five services, available to guests (`/api/v1/guest/...`, header `X-Guest-Token`) and registered users (`/api/v1/...`, bearer token) through the same code. Upload a resume / job description first with `POST .../documents`, then call:

| Endpoint | Input | Output |
|---|---|---|
| `POST /resume/analyze` | `document_id`, optional `report_format` (`pdf`/`docx`) | profile, skills with evidence, leadership evidence, employment, years, education, certifications, quality score, strengths, weaknesses, missing information, ATS recommendations |
| `POST /job-description/analyze` | `document_id` | title, company, min years, mandatory/preferred/optional skills, responsibilities, education, leadership, architecture, domain, communication |
| `POST /career/match` | resume + JD ids, `include_narrative` (default false) | overall + category scores, matching / partial / missing skills with resume evidence, recommendations |
| `POST /career/skill-gap` | resume + JD ids, `declared_absent_skills` | gaps with status, severity, current evidence, required competency, learning recommendations, exercises, timeline |
| `POST /resume/optimize` | resume + JD ids, `confirmed_skills`, `approved_change_ids`, `declined_change_ids` | before/after changes, optimised resume text, keyword recommendations, clarification questions, pending approvals |

Reports: pass `report_format` to also get a `report_id` (optimise returns two: the change report and the optimised resume file); download with `GET .../reports/{id}/download`; `GET .../reports` lists history.

## Design: deterministic first, LLM optional
- **Extraction is deterministic** (`app/career/`): a skill taxonomy with word-boundary matching, date-range parsing, section detection and phrase patterns. Nothing is inferred, so the output cannot contain skills the document does not literally mention, and instructions inside a resume cannot change results (tested: a hostile resume yields the same score as a clean one).
- **Scores are computed in code** (`matching.py`): skills weighted mandatory 1.0 / preferred 0.5 / optional 0.25; a different skill from a *substitutable* group (messaging, databases, cloud, backend, frontend, vector DBs, languages) earns partial credit (0.5, or 0.25 for languages/frontend); other groups get none. Category scores cover technical, tools, architecture, leadership, experience, domain, projects, education, certifications; categories the JD does not ask about (or, for projects, a resume without a projects section) are excluded and weights renormalised. Weights live in `ScoringConfig`. Every response carries the disclaimer that this is an estimate, not an ATS score.
- **JD skill levels:** explicit "required/must" cues, then the section heading (required/responsibilities -> mandatory, preferred/nice-to-have -> preferred), then soft cues ("strong", "proficient"); skills mentioned elsewhere without any cue are `optional`. The highest level wins.
- **Skill gaps** distinguish `not_evidenced` (the resume does not show it) from `confirmed_absent` (the user said so) and `partial`. Timelines are only 7, 15 or 60 days. Learning content is generic guidance (no invented URLs/courses).
- **Optimisation never fabricates:** minor changes (safe verb rewrites of weak bullets such as "Responsible for maintaining..." -> "Maintained...") apply by default and can be declined; significant changes (professional summary built from detected facts, skills section) apply only when their id is in `approved_change_ids`; JD skills that the resume lacks appear only under `needs_confirmation` and are added solely if the user lists them in `confirmed_skills` (sanitised). Metrics are never invented; missing metrics become clarification questions. A test asserts the optimised text contains no numbers that were not in the resume.
- **LangGraph** (`workflows/career_graph.py`) orchestrates analysis -> match -> gaps and a conditional narrative step. The optional narrative (`include_narrative`, off by default to avoid LLM cost) receives structured facts only, never raw resume text, is validated, and fails soft to `null`.
- **Reports:** `report_render.py` renders PDF (PyMuPDF Story, all text HTML-escaped) and DOCX (python-docx).

## Limitations
- Taxonomy-based: skills outside `app/career/taxonomy.py` are not detected (extend the taxonomy; no code change elsewhere). Employment parsing is heuristic and works best with dated headings and bullet lists; unusual layouts may yield fewer roles.
- Year counting uses whole years from date ranges (months are ignored) and merges overlaps.
- The scoring weights and partial-credit values are reasoned defaults, not validated against real hiring outcomes.
- English text only. Interview preparation, the coach, learning, etc. are later phases.
