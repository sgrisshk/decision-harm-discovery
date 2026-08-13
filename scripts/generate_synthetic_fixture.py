"""Generate a deterministic, entirely synthetic travel-booking fixture."""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT = Path("tests/fixtures/synthetic_travel_bookings.csv")
ROWS = 200
SEED = 20260813


def generate_row(index: int, rng: random.Random) -> dict[str, object]:
    booking_date = date(2025, 1, 1) + timedelta(days=rng.randrange(300))
    lead_time = rng.randrange(2, 150)
    travel_date = booking_date + timedelta(days=lead_time)
    supplier = rng.choice(["Atlas", "BlueWing", "Cedar", "DeltaSun"])
    customer_price = rng.randrange(700, 5200)
    discount = rng.choice([0, 0.03, 0.05, 0.08, 0.12, 0.18])
    base_cost = customer_price * rng.uniform(0.68, 0.84)
    hidden_interaction = discount > 0.10 and lead_time < 21 and supplier == "BlueWing"
    additional_cost = rng.uniform(180, 420) if hidden_interaction else rng.uniform(0, 90)
    gross_margin = customer_price * (1 - discount) - base_cost - additional_cost
    cancellation_probability = 0.22 if hidden_interaction else 0.06
    cancellation = rng.random() < cancellation_probability
    refund_amount = customer_price * (1 - discount) if cancellation else 0
    return {
        "booking_id": f"SYN-{index + 1:04d}",
        "booking_date": booking_date.isoformat(),
        "travel_date": travel_date.isoformat(),
        "destination": rng.choice(["Lisbon", "Reykjavik", "Rome", "Tokyo", "Zanzibar"]),
        "supplier": supplier,
        "customer_price": customer_price,
        "cost": round(base_cost, 2),
        "gross_margin": round(gross_margin, 2),
        "discount": discount,
        "manager": f"Manager {rng.randrange(1, 7)}",
        "acquisition_channel": rng.choice(["direct", "partner", "paid_search", "referral"]),
        "customer_type": rng.choice(["new", "returning"]),
        "party_size": rng.randrange(1, 7),
        "trip_duration": rng.randrange(3, 22),
        "booking_lead_time": lead_time,
        "payment_method": rng.choice(["card", "bank_transfer"]),
        "installments": rng.choice([1, 1, 1, 2, 3]),
        "manual_exception": rng.random() < 0.08,
        "cancellation": cancellation,
        "refund_amount": round(refund_amount, 2),
        "booking_changes": rng.randrange(0, 4),
        "support_cases": rng.randrange(0, 3) + int(hidden_interaction),
        "additional_cost": round(additional_cost, 2),
        "repeat_purchase": rng.random() < (0.12 if hidden_interaction else 0.31),
    }


def main() -> None:
    rng = random.Random(SEED)
    rows = [generate_row(index, rng) for index in range(ROWS)]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
