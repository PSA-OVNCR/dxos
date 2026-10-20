# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test kiểm PDF sau khi quét AV (Plan 01 Task 14, RF2)."""

import pytest
from dxos_core.objects.pdfcheck import check_pdf
from helpers.files import fixture


@pytest.mark.parametrize("name,reason", [("clean-text.pdf", "OK"), ("image-only.pdf", "NO_TEXT_LAYER"),  # RF2
                                         ("encrypted.pdf", "ENCRYPTED"), ("polyglot.bin", "PARSE_ERROR")])
def test_check_pdf(name, reason):
    assert check_pdf(fixture(name), 15 * 2**20).reason == reason


def test_check_pdf_empty_and_large():
    assert check_pdf(b"", 10).reason == "EMPTY"
    assert check_pdf(b"%PDF" + b"0" * 20, 10).reason == "TOO_LARGE"


@pytest.mark.parametrize("data", [b"PK\x03\x04 zip", b"MZ\x90\x00 exe", b"  %PDF-1.7 leading spaces"])
def test_bad_magic(data):
    assert check_pdf(data, 1000).reason == "BAD_MAGIC"


def test_truncated_pdf_is_parse_error():
    data = fixture("clean-text.pdf")
    assert check_pdf(data[: len(data) // 3], 10**6).reason == "PARSE_ERROR"


def test_ok_flag():
    assert check_pdf(fixture("clean-text.pdf"), 10**6).ok is True
    assert check_pdf(fixture("image-only.pdf"), 10**6).ok is False
