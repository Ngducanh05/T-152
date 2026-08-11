# Canonical F1 parking map validation

## Canonical source

[ParkSmart AI Implementation Guide — Section 5](../PARKSMART_AI_IMPLEMENTATION_GUIDE.md#5-đặc-tả-bãi-đỗ-xe-một-tầng) is the single canonical source for the F1 parking map. This file is only a validation and change-control summary; it does not define an independent map.

## ID convention

- Every floor-scoped ID starts with the F1 prefix.
- Floor: F1.
- Zones: A, B, C, and D.
- Slots: F1-{zone}{number}, where zone is A, B, C, or D and number is 01 through 10. Example: F1-C03.
- Aisle nodes: F1-{zone}-{side}, where side is W or E. Example: F1-C-E.
- Special nodes use the canonical IDs listed below.

## Map statistics

| Item | Canonical value |
|---|---:|
| Floors | 1 |
| Floor ID | F1 |
| Zones | 4: A, B, C, D |
| Slots per zone | 10 |
| Total slots | 40 |
| EV slots | 10 |
| Checkpoints | 3 |
| Entrances | 1 |
| Exits | 1 |
| Elevators | 1 |

## EV slots

- Zone C: F1-C01, F1-C02, F1-C03, F1-C04, F1-C05.
- Zone D: F1-D01, F1-D02, F1-D03, F1-D04, F1-D05.

These are the only EV slots in the canonical F1 map.

## Special nodes

| Node ID | Type | Coordinates |
|---|---|---:|
| F1-ENTRANCE | ENTRANCE | (0, 50) |
| F1-EXIT | EXIT | (100, 50) |
| F1-CP1 | CHECKPOINT | (15, 50) |
| F1-CP2 | CHECKPOINT | (50, 50) |
| F1-CP3 | CHECKPOINT | (85, 50) |
| F1-ELEVATOR | ELEVATOR | (50, 92) |

## Validation checklist

The following items are confirmed against the canonical Section 5:

- [x] There is exactly one floor, F1.
- [x] The only zones are A, B, C, and D.
- [x] Each zone has exactly 10 slots.
- [x] The map has exactly 40 slots.
- [x] The map has exactly 10 EV slots: F1-C01 through F1-C05 and F1-D01 through F1-D05.
- [x] F1-ENTRANCE exists and is the only entrance.
- [x] F1-EXIT exists and is the only exit.
- [x] F1-CP1, F1-CP2, and F1-CP3 exist and are the only three checkpoints.
- [x] F1-ELEVATOR exists and is the only elevator.
- [x] F1-ELEVATOR is located at (50, 92).
- [x] F1-ELEVATOR connects directly only to F1-C-E and F1-D-W.
- [x] There is no direct edge between F1-CP2 and F1-ELEVATOR.
- [x] Every slot references an existing node.
- [x] Every node has a path to F1-CP2.

## Map change proposal process

1. Open a proposal that identifies the exact Section 5 clauses, IDs, counts, coordinates, edges, or validation rules affected.
2. Assess the impact on the F1 ID convention, zone and slot totals, EV allocation, special nodes, graph connectivity, API contracts, and future seed or routing consumers.
3. Obtain architecture approval before changing the map contract.
4. Update Section 5 of PARKSMART_AI_IMPLEMENTATION_GUIDE.md first; do not create an alternative map specification.
5. Re-run every validation checklist item against the revised Section 5.
6. After the canonical change is approved and merged, synchronize this summary in the same change or an immediately linked documentation change.
