"""Generate synthetic, intentionally messy multi-source vendor data for Concord.

Simulates three heterogeneous vendor data sources (an ERP export, a manual
spreadsheet upload, and a partner JSON feed) that each describe an overlapping
set of real-world vendors with different schemas and different messiness
patterns. See docs/data_messiness_spec.md for exactly what's engineered here
and why.

Usage:
    uv run python scripts/generate_synthetic_data.py --n-vendors 3000 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path

from faker import Faker

SUFFIX_VARIANTS: dict[str, list[str]] = {
    "Inc.": ["Inc.", "Incorporated", "Inc", ""],
    "LLC": ["LLC", "L.L.C.", ""],
    "Corp.": ["Corp.", "Corporation", "Corp", ""],
    "Ltd.": ["Ltd.", "Limited", "Ltd", ""],
    "Co.": ["Co.", "Company", "Co", ""],
    "Group": ["Group", "Grp"],
}

STREET_TYPE_ABBR = {
    "Street": "St",
    "Avenue": "Ave",
    "Boulevard": "Blvd",
    "Drive": "Dr",
    "Lane": "Ln",
    "Road": "Rd",
    "Court": "Ct",
    "Circle": "Cir",
}

CATEGORIES = [
    "Manufacturing",
    "Logistics",
    "IT Services",
    "Professional Services",
    "Construction",
    "Healthcare Supplies",
    "Office Supplies",
    "Facilities Management",
]

CONFUSABLE_SUFFIXES = ["Group", "Holdings", "Solutions", "Partners", "Consulting"]


@dataclass
class Vendor:
    vendor_id: str
    legal_name: str
    street: str
    city: str
    state: str
    state_abbr: str
    postal_code: str
    tax_id: str  # 9 digits, no formatting
    phone: str  # 10 digits, no formatting
    category: str
    confusable_group_id: str | None = None


def generate_base_vendors(n: int, fake: Faker, rng: random.Random) -> list[Vendor]:
    vendors = []
    for i in range(n):
        state = fake.state()
        vendors.append(
            Vendor(
                vendor_id=f"V{i:06d}",
                legal_name=fake.company(),
                street=fake.street_address(),
                city=fake.city(),
                state=state,
                state_abbr=fake.state_abbr(),
                postal_code=fake.postcode(),
                tax_id=f"{rng.randint(10**8, 10**9 - 1)}",
                phone="".join(c for c in fake.numerify("##########")),
                category=rng.choice(CATEGORIES),
            )
        )
    return vendors


def add_confusable_clones(vendors: list[Vendor], n_pairs: int, rng: random.Random) -> list[Vendor]:
    """Clone a handful of vendors into distinct companies with deliberately
    similar names, to give the matching engine real hard negatives to avoid
    over-merging (see docs/data_messiness_spec.md)."""
    clones = []
    next_id = len(vendors)
    originals = rng.sample(vendors, min(n_pairs, len(vendors)))
    for group_idx, original in enumerate(originals):
        group_id = f"CG{group_idx:04d}"
        original.confusable_group_id = group_id
        base_words = original.legal_name.split()
        modified_name = " ".join(base_words[:-1] + [rng.choice(CONFUSABLE_SUFFIXES)])
        clone = Vendor(
            vendor_id=f"V{next_id:06d}",
            legal_name=modified_name,
            street=Faker().street_address(),
            city=original.city,  # same city on purpose: makes it genuinely confusable
            state=original.state,
            state_abbr=original.state_abbr,
            postal_code=Faker().postcode(),
            tax_id=f"{rng.randint(10**8, 10**9 - 1)}",
            phone="".join(c for c in Faker().numerify("##########")),
            category=original.category,
            confusable_group_id=group_id,
        )
        next_id += 1
        clones.append(clone)
    return vendors + clones


def assign_source_presence(vendors: list[Vendor], rng: random.Random) -> dict[str, list[str]]:
    """Decide which of sources A/B/C each vendor appears in. Vendors present
    in 2+ sources are the true duplicates the matching engine must find."""
    presence: dict[str, list[str]] = {}
    for v in vendors:
        roll = rng.random()
        if roll < 0.55:
            presence[v.vendor_id] = [rng.choice(["A", "B", "C"])]
        elif roll < 0.85:
            presence[v.vendor_id] = rng.sample(["A", "B", "C"], 2)
        else:
            presence[v.vendor_id] = ["A", "B", "C"]
    return presence


def vary_legal_suffix(name: str, rng: random.Random) -> str:
    for suffix, variants in SUFFIX_VARIANTS.items():
        if name.endswith(suffix):
            base = name[: -len(suffix)].rstrip()
            variant = rng.choice(variants)
            return f"{base} {variant}".strip()
    return name


def vary_connector(name: str, rng: random.Random) -> str:
    if " and " in name and rng.random() < 0.5:
        return name.replace(" and ", " & ")
    if " & " in name and rng.random() < 0.5:
        return name.replace(" & ", " and ")
    return name


def transpose_typo(s: str, rng: random.Random) -> str:
    if len(s) < 4:
        return s
    i = rng.randrange(1, len(s) - 2)
    chars = list(s)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def abbreviate_street(addr: str, rng: random.Random, prob: float) -> str:
    for full, abbr in STREET_TYPE_ABBR.items():
        if full in addr and rng.random() < prob:
            return addr.replace(full, abbr)
    return addr


def format_phone(digits: str, style: str) -> str:
    if style == "parens":
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if style == "dashes":
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if style == "intl":
        return f"+1 {digits[:3]} {digits[3:6]} {digits[6:]}"
    return digits


def format_tax_id(digits: str, dashed: bool) -> str:
    return f"{digits[:2]}-{digits[2:]}" if dashed else digits


def build_source_a_row(record_id: str, v: Vendor, rng: random.Random) -> dict:
    """ERP export: clean, consistent schema, split address fields. Light,
    occasional messiness only (legal-suffix drift, rare case noise)."""
    name = v.legal_name
    if rng.random() < 0.2:
        name = vary_legal_suffix(name, rng)
    if rng.random() < 0.05:
        name = name.upper()
    return {
        "vendor_id_src": record_id,
        "legal_name": name,
        "address_line1": v.street,
        "city": v.city,
        "state": v.state_abbr,
        "postal_code": v.postal_code,
        "country": "United States",
        "tax_id": format_tax_id(v.tax_id, dashed=True),
        "phone": format_phone(v.phone, "dashes"),
        "category": v.category,
    }


def build_source_b_row(record_id: str, v: Vendor, rng: random.Random) -> dict:
    """Manual spreadsheet upload: messiest source. Combined address field,
    inconsistent casing, occasional typos, sometimes-missing tax ID."""
    name = v.legal_name
    if rng.random() < 0.5:
        name = vary_legal_suffix(name, rng)
    name = vary_connector(name, rng)
    if rng.random() < 0.08:
        name = transpose_typo(name, rng)
    if rng.random() < 0.15:
        name = name.upper()

    street = abbreviate_street(v.street, rng, prob=0.6)
    full_address = f"{street}, {v.city}, {v.state_abbr} {v.postal_code}, USA"

    tax_id = "" if rng.random() < 0.15 else format_tax_id(v.tax_id, dashed=rng.random() < 0.5)
    phone_style = rng.choice(["parens", "dashes", "plain"])

    return {
        "VendorName": name,
        "FullAddress": full_address,
        "EIN": tax_id,
        "ContactPhone": format_phone(v.phone, phone_style),
        "Category": v.category,
    }


def build_source_c_record(record_id: str, v: Vendor, rng: random.Random) -> dict:
    """Partner JSON feed: nested, camelCase schema. Different field naming
    for category ("vertical") and country spelling."""
    name = v.legal_name
    if rng.random() < 0.25:
        name = vary_legal_suffix(name, rng)

    street = abbreviate_street(v.street, rng, prob=0.3)

    return {
        "recordId": record_id,
        "companyName": name,
        "location": {
            "street": street,
            "city": v.city,
            "region": v.state_abbr,
            "postalCode": v.postal_code,
            "country": rng.choice(["US", "USA"]),
        },
        "identifiers": {"taxId": format_tax_id(v.tax_id, dashed=rng.random() < 0.5)},
        "contact": {"phone": format_phone(v.phone, "intl")},
        "vertical": v.category,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-vendors", type=int, default=3000)
    parser.add_argument("--n-confusable-pairs", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=Path("data/synthetic"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    Faker.seed(args.seed)
    fake = Faker()

    vendors = generate_base_vendors(args.n_vendors, fake, rng)
    vendors = add_confusable_clones(vendors, args.n_confusable_pairs, rng)
    presence = assign_source_presence(vendors, rng)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    source_a_rows, source_b_rows, source_c_records = [], [], []
    record_index_rows = []
    counters = {"A": 0, "B": 0, "C": 0}

    for v in vendors:
        for source in presence[v.vendor_id]:
            counters[source] += 1
            record_id = f"{source}-{counters[source]:06d}"
            record_index_rows.append(
                {
                    "record_id": record_id,
                    "source": source,
                    "vendor_id": v.vendor_id,
                    "confusable_group_id": v.confusable_group_id or "",
                }
            )
            if source == "A":
                source_a_rows.append(build_source_a_row(record_id, v, rng))
            elif source == "B":
                source_b_rows.append(build_source_b_row(record_id, v, rng))
            else:
                source_c_records.append(build_source_c_record(record_id, v, rng))

    _write_csv(args.out_dir / "source_a_erp_export.csv", source_a_rows)
    _write_csv(args.out_dir / "source_b_manual_upload.csv", source_b_rows)
    (args.out_dir / "source_c_partner_feed.json").write_text(json.dumps(source_c_records, indent=2))
    _write_csv(args.out_dir / "record_index.csv", record_index_rows)

    ground_truth_pairs = _build_ground_truth_pairs(record_index_rows)
    _write_csv(args.out_dir / "ground_truth_pairs.csv", ground_truth_pairs)

    print(f"Vendors generated: {len(vendors)} ({args.n_confusable_pairs} confusable clones)")
    print(
        f"Records — source A: {len(source_a_rows)}, "
        f"source B: {len(source_b_rows)}, source C: {len(source_c_records)}"
    )
    print(f"True duplicate pairs (ground truth): {len(ground_truth_pairs)}")


def _build_ground_truth_pairs(record_index_rows: list[dict]) -> list[dict]:
    by_vendor: dict[str, list[dict]] = {}
    for row in record_index_rows:
        by_vendor.setdefault(row["vendor_id"], []).append(row)

    pairs = []
    for vendor_id, records in by_vendor.items():
        if len(records) < 2:
            continue
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                pairs.append(
                    {
                        "record_id_1": records[i]["record_id"],
                        "source_1": records[i]["source"],
                        "record_id_2": records[j]["record_id"],
                        "source_2": records[j]["source"],
                        "vendor_id": vendor_id,
                    }
                )
    return pairs


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
