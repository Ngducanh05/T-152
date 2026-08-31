# ParkSmart Points and parking vouchers

Status: implemented for earning, signed balance, catalog, redemption, voucher issuance,
expiry, application to an owned active parking session, wallet display, and duration-only
time-benefit reporting on session completion. Pricing, checkout, payment, tariffs, invoices,
and money amounts remain deliberately out of scope.

Personal points, ledger history and vouchers live in the ParkSmart Points popup, not in the
conversation. The Agent may read only general configuration and the active catalog; it cannot
read a personal balance or voucher wallet and cannot redeem, apply, or refund anything.

Verified adjacent observations earn the configured 10 points and confirmed wrong-parking
reports earn the configured 20 points. Contribution allocation is capped at 100 points per
Asia/Ho_Chi_Minh business day; the remaining amount is reserved when a requested reward would
cross the cap. Only finalized `EARNED` amounts are available for spending.

The database catalog seeds exactly these operator-editable defaults: `PARKING_15M` (100 points,
15 minutes), `PARKING_30M` (200, 30), and `PARKING_60M` (400, 60). A redemption atomically
creates a negative `POSTED` ledger entry, redemption record and one user-owned voucher. Voucher
snapshots remain unchanged if the catalog is edited later. Vouchers are one-time, non-transferable,
have no cash value, expire after their snapshot validity (30 days for the defaults), and do not
automatically refund points on expiry.

## Application and time benefit

The implemented flow is:

```text
Rewards UI -> RewardRedemptionService -> signed ledger -> issued voucher
-> VoucherApplicationService -> active ParkingSession -> completed session
-> ParkingTimeBenefitService -> future PricingService
```

`VoucherApplicationService` locks the user, session and voucher, checks ownership, lazy expiry
and the existing partial unique `applied_session_id` guard, then marks one `ISSUED` voucher as
`APPLIED`. A voucher is non-transferable, has no cash value, is not automatically refunded on
expiry, and unused free minutes are forfeited. Applying a voucher does not touch the reward
ledger or parking state.

`ParkingTimeBenefitService` uses exact duration arithmetic after completion:
`total_minutes = max(0, completed_at - parked_at) / 60`, then caps free time at the voucher
snapshot and returns the remainder as billable minutes. It does not round, price, charge or
create any checkout record. `ParkingSessionService` remains lifecycle-only.

## Controlled redemption rollout

`REWARDS_REDEMPTION_ENABLED=false` is fail-closed on the backend. The browser also requires
`NEXT_PUBLIC_REWARDS_REDEMPTION_ENABLED=true`; it hides catalog/redeem mutations unless both
flags allow the capability. The backend is authoritative and returns `REDEMPTION_DISABLED` if
redemption is disabled. Existing balances, pending amounts, history, issued vouchers and voucher
application remain available while the flag is off.

No durable product policy currently defines a redemption rate limit. The implementation therefore
does not invent one; authorization, idempotency, row locking, ownership checks and non-negative
finalized balance remain the correctness controls.
