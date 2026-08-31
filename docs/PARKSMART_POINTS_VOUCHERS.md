# ParkSmart Points and parking vouchers

Status: implemented for earning, signed balance and ledger history, catalog, feature-gated
redemption, voucher issuance/expiry/wallet display, active-session application and completion
time benefit. Pricing, checkout and payment are deliberately not implemented.

The assistant may read only the public reward configuration and authoritative catalog. It cannot
read or infer a user's balance, wallet or ledger, and it has no reward mutation tools. Personal
reward information and redemption remain deterministic ParkSmart Points UI actions.

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

## Voucher application and ledger

The catalog and signed Points ledger are database-driven. New point redemption is fail-closed unless `REWARDS_REDEMPTION_ENABLED=true`; the frontend additionally requires `NEXT_PUBLIC_REWARDS_REDEMPTION_ENABLED=true`, but the backend remains authoritative.

Issued vouchers can be applied once to an active owned parking session. A session has at most
one applied voucher. Completion returns a time-only benefit (`total_minutes`, `free_minutes`,
`billable_minutes`); ParkSmart does not model pricing, payments, or money.
`GET /rewards/users/{user_id}/ledger` exposes the complete signed ledger, including redemption
debits.
