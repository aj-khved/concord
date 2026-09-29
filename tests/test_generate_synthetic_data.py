import importlib.util
import random
import sys
from pathlib import Path

from faker import Faker

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "generate_synthetic_data.py"
_spec = importlib.util.spec_from_file_location("generate_synthetic_data", SCRIPT_PATH)
gen = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gen  # dataclass() needs the module registered before exec
_spec.loader.exec_module(gen)


def test_generated_vendors_have_unique_ids():
    rng = random.Random(1)
    Faker.seed(1)
    vendors = gen.generate_base_vendors(50, Faker(), rng)
    ids = [v.vendor_id for v in vendors]
    assert len(ids) == len(set(ids))


def test_confusable_clones_share_group_and_differ_in_identity():
    rng = random.Random(1)
    Faker.seed(1)
    vendors = gen.generate_base_vendors(20, Faker(), rng)
    vendors = gen.add_confusable_clones(vendors, n_pairs=3, rng=rng)

    grouped: dict[str, list] = {}
    for v in vendors:
        if v.confusable_group_id:
            grouped.setdefault(v.confusable_group_id, []).append(v)

    assert len(grouped) == 3
    for group in grouped.values():
        assert len(group) == 2
        assert group[0].vendor_id != group[1].vendor_id
        assert group[0].legal_name != group[1].legal_name


def test_ground_truth_pairs_only_link_multi_source_vendors():
    record_index_rows = [
        {"record_id": "A-1", "source": "A", "vendor_id": "V1", "confusable_group_id": ""},
        {"record_id": "B-1", "source": "B", "vendor_id": "V1", "confusable_group_id": ""},
        {"record_id": "A-2", "source": "A", "vendor_id": "V2", "confusable_group_id": ""},
    ]
    pairs = gen._build_ground_truth_pairs(record_index_rows)
    assert len(pairs) == 1
    assert pairs[0]["vendor_id"] == "V1"
    assert {pairs[0]["record_id_1"], pairs[0]["record_id_2"]} == {"A-1", "B-1"}
