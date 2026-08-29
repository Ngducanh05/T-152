# ParkSmart Points and parking vouchers

Status: implemented for earning, signed balance, catalog, redemption, voucher issuance,
expiry and wallet display. Pricing, checkout, payment and attaching a voucher to a completed
parking session are deliberately not implemented.

The assistant has read-only access to the authoritative reward configuration, balance, catalog
and owned voucher wallet; redemption remains a deterministic Rewards UI action. Wrong-parking
evidence supports either camera capture or gallery selection, both feeding the same optional
validated image upload pipeline.

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

Future checkout may attach no more than one voucher to a session and calculate
`max(0, parking_minutes - free_minutes_snapshot)`. No tariff, price, invoice, payment, or
voucher application behavior exists in the current parking lifecycle.
