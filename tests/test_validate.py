"""Test suite for graphe-verification-framework."""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import create_app
from validate import (
    GREEK_FIELD_PATTERN,
    GREEK_TOKEN_PATTERN,
    SCHEMA_PATH,
    VerificationEngineError,
    normalize_nfc,
    verify_passage,
)


@pytest.fixture(scope="module")
def schema_validator() -> Draft202012Validator:
    """Compile the Draft 2020-12 validator from schema/analysis.json."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture()
def client():
    """Create a Flask test client."""
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


def _assert_schema_and_greek_nfc(result: dict, validator: Draft202012Validator) -> None:
    """Assert payload validates against schema/analysis.json and uses NFC Greek fields."""
    errors = list(validator.iter_errors(result))
    assert errors == [], f"Schema validation errors: {[e.message for e in errors]}"

    greek_text = result["greek_text"]
    assert greek_text == unicodedata.normalize("NFC", greek_text)
    assert GREEK_FIELD_PATTERN.match(greek_text)

    for citation in result["citations"]:
        assert citation["greek_excerpt"] == unicodedata.normalize("NFC", citation["greek_excerpt"])
        assert GREEK_FIELD_PATTERN.match(citation["greek_excerpt"])

    for token in result["morphology"]:
        assert token["surface_form"] == unicodedata.normalize("NFC", token["surface_form"])
        assert token["lemma"] == unicodedata.normalize("NFC", token["lemma"])
        assert GREEK_TOKEN_PATTERN.match(token["surface_form"])
        assert GREEK_TOKEN_PATTERN.match(token["lemma"])


def test_passing_passage_john_6_63(schema_validator: Draft202012Validator) -> None:
    """Verify a clean, non-excluded stored passage passes all 10 criteria."""
    result = verify_passage("John 6:63")
    _assert_schema_and_greek_nfc(result, schema_validator)

    assert result["overall_verdict"] == "PASS"
    assert result["excluded"] is False
    assert result["failed_criteria"] == []
    assert result["failure_reasons"] == []
    assert result["corpus"] == "nt"
    assert result["source_file"] == "store/nt/gospels.json"
    assert result["verse_anchor"] == "John.6.63"
    assert len(result["citations"]) >= 1
    assert len(result["criteria_evaluations"]) == 10
    assert all(item["status"] == "PASS" for item in result["criteria_evaluations"])


@pytest.mark.parametrize(
    "excluded_query,expected_corpus",
    [
        ("Hebrews 4:12", "excluded_unknown"),
        ("Song of Solomon 1:1", "excluded_unknown"),
        ("Jude 1:3", "excluded_unknown"),
        ("James 1:2", "excluded_unknown"),
        ("Revelation 1:1", "excluded_unknown"),
        ("John 7:53-8:11", "nt"),
        ("Mark 16:9-20", "nt"),
        ("Romans 13:1-7", "nt"),
        ("1 John 5:7-8", "nt"),
        ("Deuteronomy 20:16-18", "lxx"),
        ("1 Samuel 15:3", "lxx"),
        ("Genesis 9:20-27", "lxx"),
        ("Genesis 19:6-8", "lxx"),
    ],
)
def test_exclusion_gate_enforced_fail_closed(
    excluded_query: str,
    expected_corpus: str,
    schema_validator: Draft202012Validator,
) -> None:
    """Verify excluded books and passages fail closed with schema-valid output."""
    result = verify_passage(excluded_query)
    _assert_schema_and_greek_nfc(result, schema_validator)

    assert result["excluded"] is True
    assert result["overall_verdict"] == "FAIL"
    assert len(result["failed_criteria"]) >= 1
    assert len(result["failure_reasons"]) >= 1
    assert result["corpus"] == expected_corpus
    assert len(result["citations"]) >= 1


def test_fail_closed_on_unstored_known_book(schema_validator: Draft202012Validator) -> None:
    """Verify a known book with an unstored verse fails closed with no invented claim."""
    result = verify_passage("Genesis 99:99")
    _assert_schema_and_greek_nfc(result, schema_validator)

    assert result["overall_verdict"] == "FAIL"
    assert result["excluded"] is False
    assert result["corpus"] == "not_loaded"
    assert result["source_file"] == "store/"
    assert len(result["failed_criteria"]) >= 1
    assert len(result["failure_reasons"]) >= 1
    assert result["morphology"] == []


def test_fail_closed_on_fake_reference() -> None:
    """Verify completely unknown/fake references raise VerificationEngineError."""
    with pytest.raises(VerificationEngineError):
        verify_passage("FakeBook 99:99")


def test_nfc_normalization_and_bilingual_query(schema_validator: Draft202012Validator) -> None:
    """Verify NFD input and Greek book queries normalize cleanly to NFC."""
    nfd_query = unicodedata.normalize("NFD", "John 6:63")
    assert normalize_nfc(nfd_query) == unicodedata.normalize("NFC", "John 6:63")

    res_nfd = verify_passage(nfd_query)
    _assert_schema_and_greek_nfc(res_nfd, schema_validator)
    assert res_nfd["overall_verdict"] == "PASS"

    res_greek = verify_passage("Κατὰ Ἰωάννην 6:63")
    _assert_schema_and_greek_nfc(res_greek, schema_validator)
    assert res_greek["verse_anchor"] == "John.6.63"
    assert res_greek["overall_verdict"] == "PASS"


def test_flask_index_route(client) -> None:
    """Verify GET / returns 200 and renders the verification form."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Verification Framework" in response.get_data(as_text=True)


def test_flask_verify_form_route(client, schema_validator: Draft202012Validator) -> None:
    """Verify POST /verify renders analysis for valid and excluded queries."""
    ok_resp = client.post("/verify", data={"reference": "John 6:63"})
    assert ok_resp.status_code == 200
    ok_html = ok_resp.get_data(as_text=True)
    assert "VERDICT: PASS" in ok_html
    assert "John.6.63" in ok_html

    excl_resp = client.post("/verify", data={"reference": "Hebrews 4:12"})
    assert excl_resp.status_code == 200
    excl_html = excl_resp.get_data(as_text=True)
    assert "VERDICT: FAIL" in excl_html
    assert "EXCLUDED" in excl_html

    # Confirm direct engine output for the same query is schema-valid
    engine_res = verify_passage("Hebrews 4:12")
    _assert_schema_and_greek_nfc(engine_res, schema_validator)


def test_flask_api_verify_route(client, schema_validator: Draft202012Validator) -> None:
    """Verify GET and POST /api/verify return schema-valid JSON or 400 on bad input."""
    get_resp = client.get("/api/verify", query_string={"ref": "John 6:63"})
    assert get_resp.status_code == 200
    get_data = get_resp.get_json()
    _assert_schema_and_greek_nfc(get_data, schema_validator)
    assert get_data["overall_verdict"] == "PASS"

    post_resp = client.post("/api/verify", json={"reference": "John 7:53-8:11"})
    assert post_resp.status_code == 200
    post_data = post_resp.get_json()
    _assert_schema_and_greek_nfc(post_data, schema_validator)
    assert post_data["overall_verdict"] == "FAIL"
    assert post_data["excluded"] is True

    bad_resp = client.post("/api/verify", json={"reference": "FakeBook 99:99"})
    assert bad_resp.status_code == 400
    bad_data = bad_resp.get_json()
    assert bad_data["overall_verdict"] == "FAIL"