# ADR 002: Reward redemption and voucher application boundaries

## Status

Accepted

## Context

ParkSmart Points already uses a signed ledger, atomic redemptions and issued
parking vouchers. The product needs an owned voucher to provide parking time on
one active session, without introducing a money price, payment, or checkout
system. Personal reward data also needs a dedicated UI instead of appearing in
the parking assistant conversation.

## Decision

- The signed reward ledger remains the authoritative available-points balance.
  `PENDING` contribution entries are not spendable; earned contribution entries
  and posted non-contribution entries determine the finalized balance.
- Migration `20260830_0016` is preserved as immutable history. Its catalog,
  redemption, voucher, snapshot and partial unique applied-session design remains
  the persistence contract.
- Redemption remains atomic in a caller-owned transaction: lock the user and
  catalog row, calculate the authoritative balance, write one negative `POSTED`
  ledger entry, create one redemption and issue one voucher. The API uses the
  shared idempotency record so an ambiguous retry replays the same result.
- Catalog values are copied into redemption and voucher snapshots. Later catalog
  edits never change an already-issued voucher.
- `REWARDS_REDEMPTION_ENABLED` is backend authoritative and fail-closed. When
  disabled, catalog redemption mutations are rejected but existing balances,
  histories, issued vouchers, expiry and voucher application continue working.
  The frontend also uses `NEXT_PUBLIC_REWARDS_REDEMPTION_ENABLED` only to hide
  mutation UI; both flags must permit an effective frontend redemption.
- `VoucherApplicationService` owns application of exactly one issued voucher to
  one owned, active parking session. It validates ownership, lazy expiry and the
  one-voucher-per-session invariant under database locks. Vouchers are
  non-transferable, single-use, have no cash value, and expiry never refunds
  points automatically.
- Session ownership is enforced at the API and service boundary. Applying a
  voucher never changes the reward ledger or slot/recommendation state.
- `ParkingSessionService` remains lifecycle-only. `ParkingTimeBenefitService`
  computes elapsed, free and billable duration after completion; it does not
  price parking. A future `PricingService`, if introduced, converts billable
  time into money.
- The Agent remains an orchestrator. It cannot redeem, apply or refund vouchers,
  and it does not fetch personal balances or vouchers. Personal reward state
  lives in the ParkSmart Points UI.

## Consequences

- A completed session response can report duration benefit while preserving the
  original parking-session fields.
- There is deliberately no tariff, currency, invoice, payment, automatic
  voucher application, or refund flow.
- Redemption rate policy remains a product decision. Existing idempotency,
  locking, ownership checks and no-negative-balance rules protect correctness
  until a durable, configured policy is accepted.
