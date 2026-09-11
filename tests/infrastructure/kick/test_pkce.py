import base64
import hashlib

from twick_hub.infrastructure.kick.pkce import generate_pkce_pair, generate_state


def test_challenge_is_the_sha256_of_the_verifier():
    pair = generate_pkce_pair()
    digest = hashlib.sha256(pair.verifier.encode()).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=")
    assert pair.challenge == expected.decode()


def test_challenge_has_no_base64_padding():
    pair = generate_pkce_pair()
    assert "=" not in pair.challenge
    assert "=" not in pair.verifier


def test_successive_pairs_are_different():
    a = generate_pkce_pair()
    b = generate_pkce_pair()
    assert a.verifier != b.verifier
    assert a.challenge != b.challenge


def test_state_values_are_unique():
    assert generate_state() != generate_state()
