# Ratings, testimonials, moderation and sharing (Phase 12)

No schema change: the `feedback`, `testimonials`, `testimonial_share_events` and `moderation_logs`
tables already existed (migration 0001), so there is no new migration.

## Ratings
`POST /api/v1/feedback` (registered users): `feature` (one of the eight in `FEEDBACK_FEATURES`),
`rating` 1-5, optional `comment`. Limit: 20 per user per 24 hours. `GET /feedback` lists your own.
`GET /feedback/stats` (public) returns only the count and average.

## Testimonials
| Route | Purpose |
|---|---|
| `POST /testimonials` | Create (max 5 per user). Starts `pending`; `public_consent` defaults to **false**. |
| `GET/PATCH/DELETE /testimonials/{id}` | Owner preview, edit, delete. 404 for anyone else's id. |
| `POST /testimonials/{id}/withdraw-consent` | Immediate withdrawal. |
| `GET /testimonials/{id}/share` | Share links and text (only while public). |
| `GET /testimonials/public`, `/public/{id}` | Public list and item. |
| `GET /testimonials/public/{id}/card.png` | Branded 1200x630 PNG download. |
| `POST /testimonials/public/{id}/events` | Aggregate share counter (204). |

A testimonial is public only when **status = approved AND consent given AND not withdrawn AND not
deleted**. Every other case returns the same 404, including the card and event routes.

* **Edits reset review.** Changing any content field returns an approved, flagged or rejected
  testimonial to `pending`, so approved text can never change silently.
* **Consent.** Withdrawal clears public display immediately and is audit-logged
  (`testimonial.consent_withdrawn`). Granting consent again needs a new moderator approval.
* **Delete** scrubs the text, story and display name and keeps only the moderation trail.
  **Account deletion** removes the user's feedback, testimonials, share events and moderation logs.
* The public view contains id, text, feature, rating, would_recommend, success story and display
  name (or "Anonymous learner"). It never contains an email, user id or account name.
* Control characters and `<`/`>` are stripped on input; the card HTML-escapes everything it draws.

## Moderation (admin role)
`GET /admin/testimonials?status=`, `GET /admin/testimonials/{id}`,
`POST /admin/testimonials/{id}/moderate` with `action` in approve | reject | flag | remove and an
optional note.

| Action | Allowed from | Result |
|---|---|---|
| approve | pending, flagged, rejected | approved (needs active consent) |
| reject | pending, flagged, approved | rejected |
| flag | pending, approved | flagged |
| remove | any live state | removed (final; the author cannot edit it) |

Every action writes a `ModerationLog` row (who, previous and new status, note) and an audit-log entry.
`review_hints` (links, email addresses, phone-like numbers, shouting, missing consent) are advisory
and computed on read; they never change a status.

## Sharing
Only **LinkedIn, WhatsApp and Facebook**. `GET /testimonials/{id}/share` returns the public URL,
ready text and three links that open each platform's own share dialog. The user reviews and posts
there; this platform never posts and never claims a post was made. The frontend adds "copy link",
"copy text" and the browser's native share sheet, and records them with the events route.

## Analytics and export
Share events store only testimonial id, platform, event type and time: no user, IP or device.
`GET /admin/feedback/analytics` returns rating totals, averages by feature, the distribution,
testimonials by status and share counts. `GET /admin/feedback/export.csv` exports those aggregates
only (no comments, names or testimonial text) and writes an audit entry.

## Limits
* Moderation is manual; the hints are simple pattern checks, not a content classifier.
* The PNG card uses PyMuPDF's built-in fonts, so scripts without a bundled glyph set may show
  fallback glyphs. It renders without error for non-Latin text, but this was not visually reviewed.
* Public rate limiting is in-process (`PUBLIC_FEEDBACK_REQUESTS_PER_MINUTE`), suited to one instance.
* The React forms, share buttons and admin queue UI belong to the frontend phase.
