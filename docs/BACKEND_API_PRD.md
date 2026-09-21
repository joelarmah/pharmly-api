# Pharmly Backend API — PRD

**Audience:** an engineering team/agent building this backend from scratch, with no prior context on the Pharmly mobile app, using **FastAPI**.

**Status:** the mobile app (Flutter) currently has *no backend* — every network call below is short-circuited client-side with mock data (`if (!Env.isProd)` branches throughout the codebase) so the app is fully clickable without a server. This document specifies exactly what to build so those branches can be deleted and the app can go live against a real API, with zero client-side changes to request/response shapes (they're written to match what the client already sends and expects).

---

## 1. Goals

Build the REST API that powers:

1. **Auth** — phone number + SMS OTP + 6-digit PIN (no passwords, no email/password login)
2. **Prescriptions** — submit a prescription (OCR already runs on-device; the server never sees raw images unless one was attached)
3. **Pharmacy pricing** — given a submitted prescription, return live price/availability quotes from real pharmacy partners
4. **Orders** — place an order against a chosen pharmacy quote, track its status through fulfillment/delivery
5. **Payments** — Paystack-backed checkout for card/mobile money orders, cash-on-delivery for the rest
6. **Medicine catalog** — own the drug data (name/dosage/form/unit) so it can be added to and corrected without an app release; not currently mocked (it's a bundled static asset today) but required all the same — see §5.6

Most endpoints below have a **1:1 mapping to an existing client-side mock** (see the Appendix table) and can be built to match exactly; a few (marked "new" throughout, including all of §5.6) don't exist as a client-side mock at all and need a bit more judgment — those sections say why they're needed anyway.

## 2. Non-goals (explicitly out of scope for v1)

- **Multi-device sync of local-only data.** Health Profile, "My Medications," prescription history, order history, and in-app notifications are already fully working today as **on-device SQLite** (Drift) — deliberately local-first, no server round-trip. Do not build sync endpoints for these unless a future phase asks for it (see §8).
- **Real-time courier GPS tracking.** The map on Checkout/Track Order is a placeholder today (blocked on a Google Maps API key, unrelated to this backend). This PRD includes order **status** (preparing/on the way/delivered) but not live courier lat/lng streaming — flag as a phase 2 candidate if wanted.
- **Web/admin dashboard.** Out of scope here; pharmacies/couriers updating order status is assumed to happen through *some* channel (ops team, partner API, admin panel) that calls the status-update endpoint in §5.4 — building that channel is a separate PRD.
- **Push notifications (FCM/APNs).** The in-app Notifications feed is local-only today and works without this. Deferred to phase 2.
- **Membership/subscription billing.** `User.membership_activated_at` exists on the model and is returned by the auth endpoints (§5.1), but nothing client-side currently reads it — Home's "Membership active" badge is static copy, not gated by this field. So no subscription/billing domain (plans, renewal, payment-for-membership) is needed for v1; just persist and return the field as specified.

## 3. Actors

| Actor | How they interact |
|---|---|
| **Customer** | The Flutter mobile app — everything in §5. |
| **Payment gateway (Paystack)** | Server-to-server: this backend calls Paystack's API to initialize/verify transactions, and should verify Paystack's webhook. |
| **Ops/pharmacy/courier** | Not specified by this PRD. No dedicated `PATCH /orders/{id}/status` endpoint exists (§5.4) — `Order.progress` is updated via the admin panel for now, until a real ops/courier channel exists to justify a public endpoint (§9). |

## 4. Cross-cutting requirements

### 4.1 Base URL & environments
The client is already built for this — see `lib/core/config/env.dart`. It calls whatever `API_BASE_URL` is passed via `--dart-define` at build time (`https://api-dev.pharmly.app/v1` is the current default). Stand up matching **dev / staging / prod** environments; no code change needed on the client to point at a real host once one exists.

**Implemented:** every endpoint path in this document is mounted under `/v1` on the server (`app/main.py`), matching the client's base URL above — `POST /auth/otp/request` is actually served at `POST /v1/auth/otp/request`, and so on for every path in §5. `/health`, `/docs`, `/admin`, and `/uploads` are infra/tooling routes, not versioned API surface, and stay unprefixed. Local dev: `http://localhost:8000/v1/...`.

### 4.2 Auth scheme
- **JWT access + refresh tokens.** Every authenticated endpoint expects `Authorization: Bearer <access_token>`.
- Access tokens: short-lived (recommend 15–30 min). Refresh tokens: long-lived (recommend 30 days), single-use or rotating.
- **The client does not yet call a refresh endpoint** — it just stores whatever `access_token`/`refresh_token` it receives at login/registration/PIN-reset. **Add `POST /auth/token/refresh`** (§5.1) as part of this build even though no current mock calls it; a production app cannot work with only a 15-30 min token and no refresh path. Flag to the mobile team that they need to wire this in before going live (small change: an interceptor on 401 that calls refresh and retries).
- PINs are 6 digits, **not** passwords — never log them, hash with bcrypt/argon2, never return them in any response.

### 4.3 Error response shape
The client's error mapper (`ApiClient.mapError`) reads a `message` field off any non-2xx JSON body:

```json
{ "message": "Human-readable, already safe to show the user." }
```

Return this shape (a `message` string key) on every 4xx/5xx. FastAPI's default `HTTPException(detail=...)` serializes as `{"detail": "..."}` by **default** — override this (a custom exception handler mapping `detail` → `message`, or just always raise with a `message` key in `detail`) so client error text renders instead of falling back to a generic "Something went wrong."

### 4.4 Idempotency & timeouts
- Client request/connect/receive timeout is 30s (`Env.requestTimeoutSeconds`) — respond well within that, especially `POST /orders/pricing` (§5.3) which the client shows a loading state for.
- `POST /orders` (place order) and the Paystack initialize call should be **idempotent** per client-generated reference/idempotency key — a retried request (e.g. after a timeout where the first attempt actually succeeded) must not double-charge or double-place.

### 4.5 Rate limiting & abuse prevention
- `POST /auth/otp/request`: rate-limit per phone number (e.g. 1 per 60s, 5 per hour) — this sends a real SMS and costs money per send.
- `POST /auth/login`, `POST /auth/pin/verify`, `POST /auth/pin/change`: lock out / backoff after N consecutive wrong-PIN attempts per account (the client already has UX for a PIN-mismatch error — see §5.1 — so a 429/423 here should map to a clear `message`).
- OTP codes: 6 digits, single-use, expire in ~5 minutes.

### 4.6 Identifiers

All server-generated primary key ids (`users.id`, `prescriptions.id`, `medications.id`, `pharmacies.id`, `medication_catalog.id`, `admin_users.id`, etc.) are **UUIDv7** strings, e.g. `"0191b1f0-7e2a-7c3b-9b1a-2f6a4e8c1d3f"`. UUIDv7 embeds a millisecond timestamp in its high bits, so ids sort chronologically by creation time (unlike UUIDv4) while staying globally unique and unguessable enough for a public-facing id. Ids in earlier example payloads throughout this document (`"usr_..."`, `"PR123456"`, `"ph_1"`, `"cat_xxx"`) are illustrative placeholders only — the client treats ids as opaque strings and does not parse or validate their format.

---

## 5. Domains & endpoints

### 5.1 Auth

Every flow below matches `lib/features/auth/data/auth_repository.dart` exactly.

**`POST /auth/otp/request`** — send an OTP. Used by both Sign Up and Forgot PIN.
```json
// Request
{ "phone_number": "+233241234567" }
// Response: 204 No Content (or 200 {})
```

**`POST /auth/otp/verify`** — check the code the user typed.
```json
// Request
{ "phone_number": "+233241234567", "code": "123456" }
// Response 200
{ "verification_token": "short-lived-opaque-or-jwt-string" }
```
`verification_token` authorizes the *next* step (register / reset PIN) without re-sending the OTP. Recommend a short-lived (~10 min) signed JWT scoped to that one phone number + purpose (`signup` vs `forgot_pin`), so `POST /auth/register` / `POST /auth/pin/reset` can validate it stayed for the same phone number and hasn't been reused past its purpose.

**`POST /auth/register`** — final step of Sign Up (after "Your Details" + "Create PIN").
```json
// Request
{
  "verification_token": "...",
  "phone_number": "+233241234567",
  "full_name": "August Mensah",
  "email": "august@example.com",
  "pin": "123456"
}
// Response 201
{
  "access_token": "...",
  "refresh_token": "...",
  "user": {
    "id": "usr_...",
    "phone_number": "+233241234567",
    "full_name": "August Mensah",
    "email": "august@example.com",
    "address": null,
    "avatar_url": null,
    "membership_activated_at": "2026-09-16T12:00:00Z"
  }
}
```
`membership_activated_at` drives the "Membership active" badge on Home — set it at registration.

**`POST /auth/pin/reset`** — Forgot PIN's final step.
```json
// Request
{ "verification_token": "...", "pin": "123456" }
// Response 200 — same shape as /auth/register's response
```
Note: the client sends `phone_number` too in some cases (see repository source) — accept it but the phone number should really come from the validated `verification_token`, not be trusted from the request body alone.

**`POST /auth/login`**
```json
// Request
{ "phone_number": "+233241234567", "pin": "123456" }
// Response 200 — same session shape as above
// Response 401 on wrong PIN — { "message": "PIN doesn't match. Please try again." }
```

**`POST /auth/pin/verify`** — Change PIN step 1: check the *current* PIN before letting the user pick a new one.
```json
// Request
{ "phone_number": "+233241234567", "pin": "123456" }
// Response 200 {} on success, 401 with a message on mismatch
```

**`POST /auth/pin/change`** — authenticated (Bearer token required).
```json
// Request
{ "phone_number": "+233241234567", "current_pin": "123456", "new_pin": "654321" }
// Response 200 — same session shape (may just return the user, tokens optional if you don't rotate on PIN change)
```

**`POST /auth/token/refresh`** *(new — not yet called by the client, see §4.2)*
```json
// Request
{ "refresh_token": "..." }
// Response 200
{ "access_token": "...", "refresh_token": "..." }
```

**`GET /me`** *(new — not yet called by the client; currently the app just caches whatever `register`/`login` returned)*
```json
// Response 200 — the same `user` object shape as above
```
Add this so a reinstalled app / cleared cache can restore the profile instead of only ever trusting what's on-device.

**`PATCH /me`** *(new — backs Account screen's "Save Changes," currently local-only)*
```json
// Request (all optional — send only changed fields)
{ "full_name": "...", "email": "...", "address": "..." }
// Response 200 — the updated `user` object
```

**`POST /auth/logout`** *(new, optional but recommended)* — revoke the refresh token server-side. The client currently just clears its local tokens; add this so a stolen refresh token can be invalidated.

**`DELETE /me`** *(new — the Account screen's "Delete Account" button exists in the UI today but is a complete no-op client-side; it needs a real endpoint before that button can do anything, and both Apple's and Google's app store guidelines require a working account-deletion path for apps that support creating one)*.
```json
// Response 204 No Content
```
Delete or anonymize the user's PII per whatever data-retention policy the product owner sets (§9); also revoke all outstanding refresh tokens for that user.

---

### 5.2 Prescriptions

Matches `lib/features/prescriptions/data/prescriptions_repository.dart`. OCR runs on-device (Google ML Kit) — this endpoint receives the *already-extracted* medication list, plus optionally the original image for the pharmacist's reference.

**`POST /prescriptions/submit`** — `multipart/form-data`.
```
medications: <JSON array, see Medication schema below>
image: <file, optional>
```
Medication schema (each item in the array; every field is snake_case):
```json
{
  "id": "client-generated-uuid",
  "name": "Amoxicillin",
  "dosage": "500",
  "dosage_unit": "mg",
  "quantity": 21,
  "quantity_unit": "capsule",
  "type": "pills",
  "dose_amount": 1,
  "duration_days": 7,
  "reminder_enabled": true,
  "notification_days": ["Mon", "Wed", "Fri"],
  "frequency": "Twice Daily",
  "times": ["8:00 AM", "8:00 PM"],
  "start_from": "2026-09-16T08:00:00.000",
  "end_on": "2026-09-23T20:00:00.000"
}
```
Response 201 — a `Prescription`:
```json
{
  "id": "PR123456",
  "medications": [ /* same shape as above, server-assigned id is fine */ ],
  "image_url": "https://.../uploaded-image.jpg",
  "status": "submitted",
  "submitted_at": "2026-09-16T12:00:00Z"
}
```
`status` is one of `draft | submitted | priced | ordered` (only the server ever sets `priced`/`ordered`, driven by later steps in this same flow, if you choose to track prescription state that way — the mobile client does not currently drive this transition itself).

**`GET /prescriptions`** *(already implemented client-side as `fetchAll`, unused by any screen yet but present in the repository)* — returns the signed-in user's prescription history as a JSON array of the `Prescription` shape above.

---

### 5.3 Pharmacy pricing

This is the biggest *new* domain — there is no existing pharmacy/inventory model to reverse-engineer from mocks, because the mock just returns 3 hardcoded offers regardless of input. You're building this from scratch; the only fixed constraint is the **response shape** the client already parses.

**`POST /orders/pricing`**
```json
// Request
{ "prescription_id": "PR123456", "order_type": "singleLine" }  // or "multiLine"
// Response 200 — array of PharmacyOffer
[
  {
    "pharmacy_id": "ph_1",
    "pharmacy_name": "Ernest Chemists - Spintex",
    "total_price": 403.14,
    "currency": "GHS",
    "is_fully_in_stock": true,
    "rating": 4.8,
    "distance_km": 0.8,
    "eta_minutes": 25
  }
]
```
`rating`, `distance_km`, `eta_minutes` are optional (nullable) — the client already handles their absence. `currency` defaults to `"GHS"` client-side if omitted, but send it explicitly.

**Needed supporting data model (your design call):** a `Pharmacy` entity (id, name, location, rating) and some form of per-medication price list / inventory per pharmacy, so pricing can be computed from the submitted prescription's actual medications rather than hardcoded. Minimum viable: a manually-maintained price table per partner pharmacy; `distance_km` computed from the customer's delivery address (geocoded) to each pharmacy's location.

`order_type`: `singleLine` = one combined quote across all medications from a single pharmacy; `multiLine` = (per the mock's comment) a separate quote per medication — if `multiLine` support is deferred, at minimum don't error on it; treat it the same as `singleLine` until real multi-pharmacy splitting is built, and flag this to the product owner.

**Confirmed architecture (resolves part of §9 open question #4):** `pharmacy_products` (a pharmacy's listing of a catalog medication — price, stock, provenance; named "products" rather than "prices" since each row is a real inventory listing, not just a number) is always a **local cache** — `POST /orders/pricing` reads from our own database, never from a partner pharmacy live, so a burst of pricing requests never hits a partner's servers directly. Pharmacies onboard one of two ways, tracked on `Pharmacy.inventory_source` and per-row on `PharmacyProduct.source`:
- **`manual`** — an ops person enters/corrects prices directly via the admin panel (`/admin`, `app/admin.py`). This is the only *implemented* onboarding path today.
- **`partner_api`** — reserved for when a real partner pharmacy API/contract exists; a periodic sync would pull their inventory and upsert `pharmacy_products` rows with `source="partner_api"` and `synced_at` set to when that pull happened. Not implemented — there is no real partner integration to build against yet (see §9).

`PharmacyProduct.stock_quantity` exists to eventually carry real per-item stock counts once a real source (manual or partner) populates it; today it's unused by pricing logic — a row's mere existence still means "in stock," as before.

---

### 5.4 Orders

Matches `lib/features/orders/data/orders_repository.dart` + the new order-history/tracking work in the mobile app.

**`POST /orders`** — place an order. Called only after payment has already succeeded (card/mobile money) or immediately for cash.
```json
// Request
{
  "prescription_id": "PR123456",
  "pharmacy_id": "ph_1",
  "payment_type": "cashOnDelivery",       // or "card" | "mobileMoney"
  "payment_reference": null               // the Paystack transaction reference, when payment_type is card/mobileMoney; null for cash
}
// Response 201
{ "order_id": "PR151528" }
```
**Implemented, idempotent on `prescription_id` alone** (resolves the "prescription_id + pharmacy_id, or an idempotency key" question this section originally posed): a `Prescription` can only ever produce one `Order` — enforced with a DB unique constraint on `orders.prescription_id`, matching `Prescription.status`'s existing `ordered` terminal state and real pharmacy fulfillment (a script gets filled once). A retry of `POST /orders` — same request, or even a different `pharmacy_id` — returns the order that already exists rather than erroring or duplicating. This doesn't limit how often a user orders overall: each submitted prescription is a separate row with its own id, so a user places as many orders as they submit prescriptions for.

`total` is always computed server-side from `PharmacyProduct` prices at placement time — never trusted from the client. `payment_reference` (for `card`/`mobileMoney`) is accepted and stored as given; it is **not yet verified against Paystack** (§5.5 isn't built) — flagged here rather than silently trusted.

**`GET /orders`** — the signed-in user's order history, newest first. Response: array of:
```json
{
  "id": "PR151528",
  "pharmacy_name": "Ernest Chemists - Spintex",
  "items_label": "Cataflam, Amoxicillin · 2 items",
  "progress": "preparing",                 // "preparing" | "onTheWay" | "delivered"
  "placed_at": "2026-09-21T17:33:32.940907",
  "total": 403.14
}
```
**Resolved (§9 open question #5):** `date_label` (a pre-formatted display string) is replaced with a raw `placed_at` ISO timestamp. The mock's exact strings (e.g. "Arrives Jul 7, by 11:15 AM") need a real delivery ETA this backend doesn't track — rather than approximate that, the mobile team formats `placed_at` client-side.

**`GET /orders/{id}`** — single order detail (same shape as above; used by "Buy Again" on a past order).

**`PATCH /orders/{id}/status`** — **not built.** Its caller was an open question this section flagged (§9 #1) and remains unresolved — no ops/courier channel exists to call it. Rather than expose a public HTTP endpoint with nothing real to call it, `Order.progress` is updated via the admin panel (`/admin`) instead, the one real "ops channel" that exists today. A dedicated endpoint is straightforward to add once an actual courier/ops system needs to call it — this is a deliberate deviation from this section's original "expose the endpoint anyway" instruction, not an oversight.

---

### 5.5 Payments (Paystack)

Matches `lib/features/orders/data/payment_gateway_repository.dart`. **Card and Mobile Money never touch this app's own forms** — the customer completes payment on Paystack's own hosted checkout page; this backend only brokers the session and checks its outcome. Cash-on-delivery skips this domain entirely.

**`POST /payments/paystack/initialize`**
```json
// Request
{ "amount": 403.14, "email": "customer@pharmly.app", "reference": "PSK-<client-generated>" }
// Response 200
{ "reference": "PSK-...", "checkout_url": "https://checkout.paystack.com/..." }
```
Server-side: call Paystack's `POST /transaction/initialize` with your **secret** key (never exposed to the client), using the client-provided `reference` (or generate your own and return it — the client already handles the server returning a possibly-different `reference` than it sent). `amount` must be converted to Paystack's expected minor-unit format (pesewas, i.e. `× 100`) — that's a backend-only concern, the client always deals in GHS major units.

**`GET /payments/paystack/verify/{reference}`**
```json
// Response 200
{ "status": "pending" }   // or "success" | "failed"
```
The client **polls this in a loop** (every ~1.5s) showing a "Confirming Payment" dialog until it sees `success` or `failed` — keep this endpoint fast (cache Paystack's verify response for a few seconds server-side rather than hitting Paystack on every poll tick if traffic is a concern).

**`POST /payments/paystack/webhook`** *(new — strongly recommended even though the client doesn't call it)* — Paystack calls this server-to-server when a transaction completes. **Verify the `x-paystack-signature` header (HMAC-SHA512 with your secret key)** before trusting the payload. Use this as the source of truth for marking a transaction's final status (rather than only trusting client-driven polling). There is no `PATCH /orders/{id}/status` to drive (§5.4 — not built, see §9 #1); the webhook only updates `payment_transactions.status`.

**Implemented — design notes:**
- **Idempotency**: `reference` doubles as the idempotency key. A client-supplied `reference` that already has a `PaymentTransaction` row short-circuits `initialize` — returns the existing `checkout_url` instead of calling Paystack again. Omitted `reference` → server-generates one (`PSK-<uuid7>`).
- **Verify caching**: a `verify` call within `paystack_verify_cache_seconds` (default 5) of the last check returns the cached local status instead of re-hitting Paystack.
- **Status mapping** (Paystack's real statuses are richer than `pending | success | failed`): only Paystack's explicit `success` maps to `success`, only explicit `failed` maps to `failed`, everything else (including `abandoned`, `queued`, etc.) maps to `pending`. Verified live against the real Paystack test API: a freshly-initialized, completely untouched transaction already reports `abandoned` — mapping that to `failed` would show a false "Payment failed" to a client mid-poll while the user is still on Paystack's checkout page.
- **Ownership**: `payment_transactions` has a `user_id` column (beyond §6's suggested table) — `verify` 404s a reference that isn't the caller's, matching every other resource in this API.
- **`POST /orders` now actually verifies `payment_reference`** for `card`/`mobileMoney` orders (was previously accepted/stored as given): requires a `PaymentTransaction` owned by the caller, `status == "success"`, and `amount` covering the order's server-computed total — 422 otherwise. Cash orders are unaffected. `payment_transactions.order_id` is set once the order is placed.

---

### 5.6 Medicine/drug catalog

**Correction from an earlier draft of this document:** this was originally written off as "static bundled JSON, no endpoint needed." That's wrong — a catalog nobody but the mobile team (via an app release) can add to or correct is a real gap, not a non-goal. This *is* a required domain.

**Today:** "Add Medication"'s name search, and the "Type of medicine" / dosage-unit dropdowns, are backed by three JSON files bundled into the app (`assets/data/nhis_medications.json` — 549 entries sourced from Ghana's NHIS medicines list — plus derived `medication_types.json` and `dosage_units.json`). Each entry has no stable id today (matched client-side by name+dosage) and looks like:
```json
{ "name": "Acetylsalicylic Acid", "dosage": "75", "unit": "mg", "form": "tablet", "type": "pills" }
```

**Needed:** move this to a real, backend-managed catalog so drugs can be added/corrected/retired without an app release. Two sides to build:

**Customer-facing (this is what the client will call — a client-side change: swap the bundled-asset load for these calls):**

- **`GET /medications/catalog?search=<query>&limit=&cursor=`** — paginated search by name (this backs "Add Medication"'s live search-as-you-type, so keep it fast — index on name, e.g. Postgres trigram/`ILIKE` or a proper search engine if the catalog grows well past today's 549 entries).
  ```json
  // Response 200
  {
    "entries": [
      { "id": "med_1", "name": "Acetylsalicylic Acid", "dosage": "75", "unit": "mg", "form": "tablet", "type": "pills" }
    ],
    "next_cursor": null
  }
  ```
- **`GET /medications/catalog/metadata`** — the fixed dropdown option lists (medicine "type" and dosage "unit"), so these can also change without an app release:
  ```json
  { "types": ["pills", "injection", "liquid", "topical", "drops", "suppository", "inhaler", "powder", "other"],
    "dosage_units": ["mg", "%", "mg/ml", "mL", "microgram", "units", "g", "iu", "meq"] }
  ```

**Management (add/update/retire entries — who calls these is an open question, see below):**

- **`POST /medications/catalog`** — add an entry: `{ "name", "dosage", "unit", "form", "type" }` → `201` with the created entry (server-assigned `id`).
- **`PATCH /medications/catalog/{id}`** — correct an entry (e.g. a wrong dosage/unit).
- **`DELETE /medications/catalog/{id}`** — retire an entry (soft-delete recommended — don't break historical prescriptions/medications that already reference this name/dosage combo by string, since `Medication.name`/`.dosage` are copied by value onto prescriptions, not foreign-keyed to the catalog).
- **`POST /medications/catalog/import`** — bulk upsert (CSV or JSON body) keyed on name+dosage+form, for periodically re-syncing against an updated NHIS list or a partner data feed, the same way today's static asset was originally compiled. Recommend building this first and seeding day-one data straight from the existing `assets/data/nhis_medications.json` (549 entries) rather than hand-entering them.

**Open question for the product owner (add to §9):** *who* manages this catalog, and how are they authenticated? None of this app's existing auth (customer phone+OTP+PIN) is appropriate for catalog management. Cheapest v1: gate the management endpoints behind a static internal API key (`X-Admin-Key` header) for an ops person running a CLI/import script — upgrade to real staff accounts with a `role: admin` claim if/when a proper internal tool gets built. Do **not** expose the management endpoints to the customer-facing JWT scheme.

**Why an owned table instead of a third-party drug-database API:** considered and rejected for now. Global drug databases (RxNorm, openFDA, DrugBank) are US/international-centric and won't line up with what's actually registered with Ghana FDA or covered by NHIS — the current data *is* Ghana's NHIS medicines list, which is what determines what's realistically prescribed/dispensed/reimbursed locally. Pricing/availability is pharmacy-specific anyway (`pharmacy_products`, tied to real partner pharmacies) — a drug-identity API alone wouldn't provide that. Own the table; use `POST /medications/catalog/import` as the integration seam if a real Ghana-specific formulary feed (an FDA Ghana registry, an NHIS API, or a partner pharmacy's product-master feed) ever becomes available.

---

## 6. Data model summary (suggested SQLAlchemy tables)

| Table | Key fields |
|---|---|
| `users` | id, phone_number (unique), full_name, email, address, avatar_url, pin_hash, membership_activated_at, created_at |
| `otp_codes` | phone_number, code_hash, purpose (`signup`\|`forgot_pin`), expires_at, consumed_at |
| `prescriptions` | id, user_id, image_url, status, submitted_at |
| `medications` | id, prescription_id (FK), name, dosage, dosage_unit, quantity, quantity_unit, type, dose_amount, duration_days, reminder_enabled, notification_days (JSON), frequency, times (JSON), start_from, end_on |
| `pharmacies` | id, name, location (lat/lng), rating |
| `medication_catalog` | id, name, dosage, unit, form, type, retired_at (soft-delete) |
| `pharmacy_products` | pharmacy_id (FK), catalog_id (FK to `medication_catalog`), unit_price, stock_quantity, source, synced_at |
| `orders` | id, user_id, prescription_id (FK, unique -- one order per prescription), pharmacy_id (FK), payment_type, payment_reference, progress, total, placed_at |
| `payment_transactions` | reference, user_id (FK), order_id (nullable until order placed), amount, status, paystack_raw_response (JSON), created_at, last_checked_at |

## 7. Non-functional requirements

- **HTTPS only** in staging/prod.
- **Structured logging** with request IDs; never log PINs, OTP codes, or full card/payment details.
- **OpenAPI docs** (FastAPI gives you this for free at `/docs`) kept accurate — the mobile team will use it as the live contract reference.
- **Automated tests** per endpoint (FastAPI + `httpx`/`pytest`), especially the auth PIN-mismatch and OTP-expiry edge cases, and Paystack webhook signature verification.
- **Migrations** via Alembic from day one.

## 8. Explicitly deferred (phase 2+, do not build now)

- Sync endpoints for Health Profile, My Medications, prescription/order history, and Notifications — all already fully functional as on-device SQLite. Only revisit if multi-device sync becomes a real product requirement.
- Push notifications (FCM/APNs) — the in-app feed works locally today.
- Live courier GPS / WebSocket tracking.
- Multi-pharmacy order splitting for `multiLine` order type (see §5.3).

## 9. Open questions for the product owner (not this backend team to decide)

1. **Who/what calls order-status updates?** An ops dashboard? A courier-facing app? Direct pharmacy-partner API integration? Resolved for now: no dedicated endpoint exists, `Order.progress` is updated via the admin panel — revisit once a real caller (ops dashboard, courier app, etc.) exists, at which point a `PATCH /orders/{id}/status` endpoint is straightforward to add.
2. **SMS provider** for OTP delivery — resolved: Arkesel (see `app/services/sms.py`).
3. **Paystack account** — test secret key provided and wired in; §5.5 is now built and verified live against Paystack's test API (real `initialize`/`verify` round trips, real HMAC-SHA512 webhook signature verification). Still needed before going live: **live** keys, and whether Mobile Money channels are enabled on the account (Ghana MTN/Vodafone/AirtelTigo).
4. **Pharmacy partner data** — partially decided (see §5.3): pricing always reads from our own `pharmacy_products` cache, populated either by manual ops entry (implemented, via the admin panel) or a future partner API sync (not implemented — no real partner contract/credentials exist yet, same situation Arkesel was in before real docs/keys were provided). Still open:
   - No real partner pharmacy API contract exists to build `source="partner_api"` sync against — needed before that path can be implemented at all.
   - No scheduler/background-job infrastructure exists in this codebase (confirmed: no Celery/APScheduler/cron anywhere) — a periodic partner sync needs *some* execution mechanism once a real partner exists; an admin-triggered endpoint (matching the `X-Admin-Key` precedent in §5.6) is the cheapest v1 option, a real scheduler the eventual one.
   - `POST /orders/pricing`'s "scan nearby pharmacies" step is currently a naive load-all-pharmacies-then-filter-in-Python (fine at today's scale of a handful of seeded pharmacies); a real geospatial query (PostGIS `ST_DWithin` or similar) will be needed once onboarded-pharmacy volume makes that too slow — not built now to avoid premature optimization.
5. **`date_label` formatting** (§5.4) — server-formatted display string vs. raw timestamp + client-side formatting. Recommend moving to raw timestamps if the mobile team can pick this work up; otherwise this backend needs to replicate the exact display strings currently hardcoded client-side.
6. **Who manages the medicine catalog (§5.6)**, and how are they authenticated? An ops person via CLI/import script (cheapest, static API key) vs. a real internal admin tool with staff accounts. Also: is there a periodic official source (Ghana FDA/NHIS) to re-import from, or is this manual entry/correction only for now?
7. **Account deletion** — there is currently no way for a `User` to delete/close their account: no endpoint in this PRD, and no `deleted_at`/`is_active` field on the `users` table to support one. Needs a product-owner decision before it's built:
   - **Soft delete** (a `deleted_at` timestamp, filtered out of auth/lookups) preserves referential integrity for rows that reference `users.id` (`prescriptions`, `refresh_tokens`, orders once §5.4 exists) and any order/payment history, but requires excluding soft-deleted rows everywhere `User` is queried and deciding whether a re-registration with the same `phone_number` is then allowed.
   - **Hard delete** is simpler but needs `ON DELETE CASCADE`/explicit cleanup across every FK to `users.id`, and permanently loses order/prescription history that might be needed for support or legal/tax record-keeping.
   - Also relevant: is there a legal requirement (e.g. a "right to be forgotten"-style data protection obligation in Ghana) driving this, which would push toward true erasure of PII rather than a retained-but-hidden soft delete?

---

## Appendix: mock → endpoint map

For quick cross-reference against the Flutter source (`lib/features/*/data/*_repository.dart`, all gated by `if (!Env.isProd)`):

| Client method | Endpoint | Status |
|---|---|---|
| `AuthRepository.requestOtp` | `POST /auth/otp/request` | Built |
| `AuthRepository.verifyOtp` | `POST /auth/otp/verify` | Built |
| `AuthRepository.completeRegistration` | `POST /auth/register` | Built |
| `AuthRepository.resetPin` | `POST /auth/pin/reset` | Built |
| `AuthRepository.login` | `POST /auth/login` | Built |
| `AuthRepository.verifyPin` | `POST /auth/pin/verify` | Built |
| `AuthRepository.changePin` | `POST /auth/pin/change` | Built |
| *(none yet — client caches locally)* | `POST /auth/token/refresh` | Built + ask mobile team to wire in |
| *(none yet)* | `GET /me` | Built |
| *(none yet)* | `PATCH /me` | Built |
| *(none yet)* | `POST /auth/logout` | Built |
| *(none yet — "Delete Account" button is currently a no-op)* | `DELETE /me` | Built |
| `PrescriptionsRepository.submit` | `POST /prescriptions/submit` | Built |
| `PrescriptionsRepository.fetchAll` | `GET /prescriptions` | Built |
| `OrdersRepository.fetchPricing` | `POST /orders/pricing` | Built (§5.3) |
| `OrdersRepository.placeOrder` | `POST /orders` | Built |
| *(mobile app's local order history)* | `GET /orders`, `GET /orders/{id}` | Built |
| *(none yet — needed to make tracking real)* | `PATCH /orders/{id}/status` | Not built — see §9 #1 (admin panel used instead) |
| `PaymentGatewayRepository.initializeTransaction` | `POST /payments/paystack/initialize` | Built (test keys; live keys still needed, §9 #3) |
| `PaymentGatewayRepository.verifyTransaction` | `GET /payments/paystack/verify/{reference}` | Built (test keys; live keys still needed, §9 #3) |
| *(none yet — recommended)* | `POST /payments/paystack/webhook` | Built (test keys; live keys still needed, §9 #3) |
| *(currently a bundled JSON asset — client-side change needed)* | `GET /medications/catalog`, `GET /medications/catalog/metadata` | Not built |
| *(none — new management domain)* | `POST/PATCH/DELETE /medications/catalog`, `POST /medications/catalog/import` | Not built — admin panel covers hand-editing today |
