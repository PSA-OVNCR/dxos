# SPDX-FileCopyrightText: 2026 DX-OS Trust Core contributors
# SPDX-License-Identifier: Apache-2.0
import pytest
from dxos_proof.merkle import (
    consistency_proof,
    inclusion_proof,
    leaf_hash,
    root,
    verify_consistency,
    verify_inclusion,
)

L = [bytes.fromhex(x) for x in ["", "00", "10", "2021", "3031", "40414243",
                                 "5051525354555657", "606162636465666768696a6b6c6d6e6f"]]
ROOTS = {
    0: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    1: "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    2: "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    3: "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    4: "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    5: "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    6: "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    7: "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    8: "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
}


@pytest.mark.parametrize("n", range(9))
def test_roots(n):
    assert root(L[:n]).hex() == ROOTS[n]


def test_inclusion_proof_index5_size8():
    assert [h.hex() for h in inclusion_proof(5, L)] == [
        "bc1a0643b12e4d2d7c77918f44e0f4f79a838b6cf9ec5b5c283e1f4d88599e6b",
        "ca854ea128ed050b41b35ffc1b87b8eb2bde461e9e3b5596ece6b9d5975a0ae0",
        "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    ]


def test_consistency_3_to_7():
    assert [h.hex() for h in consistency_proof(3, L[:7])] == [
        "0298d122906dcfc10892cb53a73992fc5b9f493ea4c9badb27b791b4127a7fe7",
        "07506a85fd9dd2f120eb694f86011e5bb4662e5c415a62917033d4a9624487e7",
        "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
        "837dbb152e9b079010717e84e865da4ebc0fa198a806d59d31bf15accef22d0e",
    ]


def test_consistency_4_to_8():
    assert [h.hex() for h in consistency_proof(4, L)] == [
        "6b47aaf29ee3c2af9af889bc1fb9254dabd31177f16232dd6aab035ca39bf6e4"
    ]


def test_verify_all_pairs_up_to_16():
    entries = [bytes([i]) for i in range(16)]
    for n in range(1, 17):
        for i in range(n):
            assert verify_inclusion(
                leaf_hash(entries[i]), i, n, inclusion_proof(i, entries[:n]), root(entries[:n])
            )
        for m in range(1, n + 1):
            assert verify_consistency(
                m, n, root(entries[:m]), root(entries[:n]), consistency_proof(m, entries[:n])
            )


def test_tampered_proofs_fail():
    p = consistency_proof(3, L[:7])
    p[0] = bytes(32)
    assert not verify_consistency(3, 7, bytes.fromhex(ROOTS[3]), bytes.fromhex(ROOTS[7]), p)
    q = inclusion_proof(5, L)
    q[1] = bytes(32)
    assert not verify_inclusion(leaf_hash(L[5]), 5, 8, q, bytes.fromhex(ROOTS[8]))
