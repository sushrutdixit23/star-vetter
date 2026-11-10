import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import f19_prior_art as pa  # noqa: E402


def _tsv(rows):
    head = "TIC\tFP\n"
    return "#\n#   VizieR\n\n" + head + "---\t--\n" + "\n".join("%s\t%s" % r for r in rows) + "\n"


def test_parse_tsv_reads_data_and_rejects_the_stub_and_errors():
    df = pa.parse_tsv(_tsv([(11, "FP CO"), (22, "FP CO")]))
    assert list(df["TIC"]) == ["11", "22"]
    assert pa.parse_tsv("Content-Type: application/x-votable+xml\nDocumentRef: x\n#\n") is None
    assert pa.parse_tsv("#INFO\tError=The database is not currently reachable.\n") is None


def test_crossmatch_by_tic_and_by_position():
    targets = pd.DataFrame({"tic": [11, 33], "ra": [10.0, 50.0], "dec": [20.0, -10.0]})
    t1 = pd.DataFrame({"TIC": ["11", "99"], "FP": ["a", "b"]})
    assert set(pa.crossmatch(t1, targets)) == {11}
    t2 = pd.DataFrame({"_RAJ2000": ["10.0010", "80.0"], "_DEJ2000": ["20.0", "0.0"], "Name": ["near", "far"]})
    m = pa.crossmatch(t2, targets)                          # 0.001 deg * cos(20) = 3.4 arcsec: inside 5
    assert set(m) == {11} and m[11]["_sep_arcsec"] < pa.MATCH_ARCSEC
    t3 = pd.DataFrame({"_RAJ2000": ["10.0030"], "_DEJ2000": ["20.0"]})    # 10 arcsec away
    assert pa.crossmatch(t3, targets) == {}
    assert pa.crossmatch(pd.DataFrame({"x": [1]}), targets) == {}


def test_simbad_groups():
    assert pa.classify_simbad("EB*") == "eclipsing_binary" and pa.classify_simbad("EB*Algol") == "eclipsing_binary"
    assert pa.classify_simbad("Pl") == "planet_or_transit" and pa.classify_simbad("*") == "plain_star"
    assert pa.classify_simbad("RR*") == "other_variable_or_peculiar" and pa.classify_simbad("BY*") == "other_variable_or_peculiar"
    assert pa.classify_simbad(None) == "other" and pa.classify_simbad("Galaxy") == "other"


def test_toi_match_reports_disposition():
    toi = pd.DataFrame({"TIC ID": [11, 12], "TOI": ["100.01", "101.01"], "TFOPWG Disposition": ["FP", "PC"]})
    targets = pd.DataFrame({"tic": [11, 13]})
    assert pa.toi_matches(toi, targets) == {11: {"toi": "100.01", "disposition": "FP"}}
