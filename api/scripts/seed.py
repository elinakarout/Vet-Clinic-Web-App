"""Creates demo data: 1 admin, 2 vets with working hours, 2 clients, 3 pets. (Phase 1)

Idempotent -- users are matched on email, so re-running changes nothing. Pass
--reset to delete the demo rows first and rebuild them from scratch.

Run from api/ with the venv active:

    python scripts/seed.py
    python scripts/seed.py --reset
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, time
from pathlib import Path

# Allow "python scripts/seed.py" without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    ClientProfile,
    Pet,
    Role,
    Sex,
    User,
    VetAvailability,
    VetProfile,
)
from app.services.security import hash_password

# Demo passwords. Fine for a local dev database, never for anything reachable.
ADMIN_PASSWORD = "admin1234"
VET_PASSWORD = "vet1234"
CLIENT_PASSWORD = "client1234"

WEEKDAYS_MON_TO_FRI = range(0, 5)

VETS = [
    {
        "email": "vet.patel@vetclinic.test",
        "full_name": "Dr. Anita Patel",
        "specialty": "Small animal medicine",
        "license_no": "VET-1001",
        "hours": (time(9, 0), time(17, 0)),
        "slot_minutes": 30,
    },
    {
        "email": "vet.novak@vetclinic.test",
        "full_name": "Dr. Marek Novak",
        "specialty": "Surgery",
        "license_no": "VET-1002",
        "hours": (time(10, 0), time(18, 0)),
        "slot_minutes": 45,
    },
]

CLIENTS = [
    {
        "email": "client.jones@example.test",
        "full_name": "Sam Jones",
        "phone": "+44 20 7946 0011",
        "address": "12 Fern Road, Bristol BS1 4TR",
        "pets": [
            {
                "name": "Biscuit",
                "species": "Dog",
                "breed": "Border Collie",
                "sex": Sex.FEMALE,
                "date_of_birth": date(2019, 4, 12),
                "weight_kg": 17.4,
                "notes": "Nervous around clippers; muzzle-trained.",
            },
            {
                "name": "Pepper",
                "species": "Cat",
                "breed": "Domestic Shorthair",
                "sex": Sex.MALE,
                "date_of_birth": date(2021, 8, 30),
                "weight_kg": 4.9,
                "notes": None,
            },
        ],
    },
    {
        "email": "client.ali@example.test",
        "full_name": "Noor Ali",
        "phone": "+44 117 496 0022",
        "address": "3 Kestrel Lane, Bath BA2 6QN",
        "pets": [
            {
                "name": "Waffle",
                "species": "Rabbit",
                "breed": "Netherland Dwarf",
                "sex": Sex.UNKNOWN,
                "date_of_birth": date(2023, 1, 9),
                "weight_kg": 1.2,
                "notes": "Indoor housed. Due a myxomatosis booster.",
            }
        ],
    },
]

ALL_DEMO_EMAILS = (
    ["admin@vetclinic.test"] + [v["email"] for v in VETS] + [c["email"] for c in CLIENTS]
)


def _get_user(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def _reset(db: Session) -> None:
    """Delete the demo users. Profiles, pets and availability cascade away with them."""
    users = db.scalars(select(User).where(User.email.in_(ALL_DEMO_EMAILS))).all()
    for user in users:
        db.delete(user)
    db.commit()
    if users:
        print(f"Removed {len(users)} existing demo user(s) and everything owned by them.")


def seed(db: Session) -> None:
    created: list[str] = []
    skipped: list[str] = []

    # --- admin -------------------------------------------------------------
    if _get_user(db, "admin@vetclinic.test") is None:
        db.add(
            User(
                email="admin@vetclinic.test",
                hashed_password=hash_password(ADMIN_PASSWORD),
                role=Role.ADMIN,
            )
        )
        created.append("admin@vetclinic.test")
    else:
        skipped.append("admin@vetclinic.test")

    # --- vets, each with Mon-Fri working hours -----------------------------
    for spec in VETS:
        if _get_user(db, spec["email"]) is not None:
            skipped.append(spec["email"])
            continue
        user = User(
            email=spec["email"],
            hashed_password=hash_password(VET_PASSWORD),
            role=Role.VET,
        )
        start, end = spec["hours"]
        user.vet_profile = VetProfile(
            full_name=spec["full_name"],
            specialty=spec["specialty"],
            license_no=spec["license_no"],
            availability=[
                VetAvailability(
                    weekday=weekday,
                    start_time=start,
                    end_time=end,
                    slot_minutes=spec["slot_minutes"],
                )
                for weekday in WEEKDAYS_MON_TO_FRI
            ],
        )
        db.add(user)
        created.append(spec["email"])

    # --- clients, each with their pets -------------------------------------
    for spec in CLIENTS:
        if _get_user(db, spec["email"]) is not None:
            skipped.append(spec["email"])
            continue
        user = User(
            email=spec["email"],
            hashed_password=hash_password(CLIENT_PASSWORD),
            role=Role.CLIENT,
        )
        # Pets hang off the client *profile*, not off the user.
        user.client_profile = ClientProfile(
            full_name=spec["full_name"],
            phone=spec["phone"],
            address=spec["address"],
            pets=[Pet(**pet) for pet in spec["pets"]],
        )
        db.add(user)
        created.append(spec["email"])

    db.commit()

    print(f"Created {len(created)} user(s); {len(skipped)} already existed.")
    if created:
        print("\n  role     email                          password")
        print("  -------  -----------------------------  -----------")
        print(f"  ADMIN    admin@vetclinic.test           {ADMIN_PASSWORD}")
        for spec in VETS:
            print(f"  VET      {spec['email']:<29}  {VET_PASSWORD}")
        for spec in CLIENTS:
            print(f"  CLIENT   {spec['email']:<29}  {CLIENT_PASSWORD}")
        print("\n  (demo credentials -- local dev only)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the demo users (and their pets) before seeding",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.reset:
            _reset(db)
        seed(db)


if __name__ == "__main__":
    main()
