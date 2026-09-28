"""La etiqueta reproduce el panel del protocolo sobre el dataset real."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from agrosense.domain.stall_rules import stall_label

REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"

pytestmark = pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)


@pytest.fixture(scope="module")
def series():
    from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

    data = ExcelCampaignSource().read(REFERENCE_PATH.read_bytes(), REFERENCE_PATH.name)
    by_tree: dict[str, dict] = defaultdict(dict)
    for o in data.observations:
        by_tree[o.tree_id][o.campaign] = o
    return by_tree


@pytest.mark.parametrize(
    "t, at_risk, stalled",
    [(1, 651, 112), (2, 618, 153), (3, 717, 157)],
)
def test_label_reproduces_the_protocol_panel(series, t, at_risk, stalled):
    labels = [stall_label(s.get(t), s.get(t + 1)) for s in series.values()]
    known = [label for label in labels if label is not None]
    assert len(known) == at_risk
    assert sum(known) == stalled


def test_half_centimetre_tree_is_not_stalled(series):
    s = series["FR_1_31"]
    assert (s[3].height_m, s[4].height_m) == (0.24, 0.245)
    assert stall_label(s[3], s[4]) is False
