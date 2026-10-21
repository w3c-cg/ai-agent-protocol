"""Offline consistency checks for the authorization draft's schematic examples.

These checks do not verify placeholder signatures or protocol implementations.
"""

from __future__ import annotations

import base64
import hashlib
import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]


class ExampleParser(HTMLParser):
    """Decode HTML entities while preserving example whitespace, including LF."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.examples: dict[str, str] = {}
        self.json_ids: list[str] = []
        self.current: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "pre" and "example" in attrs.get("class", "").split():
            self.current = attrs["id"]
            self.examples[self.current] = ""
        if tag == "code" and self.current:
            if "language-json" in attrs.get("class", "").split():
                self.json_ids.append(self.current)

    def handle_data(self, data):
        if self.current:
            self.examples[self.current] += data

    def handle_endtag(self, tag):
        if tag == "pre":
            self.current = None


def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


class AuthorizationExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parser = ExampleParser()
        parser.feed((REPO_ROOT / "agent-authorization.html").read_text(encoding="utf-8"))
        cls.examples = parser.examples
        cls.json_examples = {
            key: json.loads(parser.examples[key], object_pairs_hook=unique_members)
            for key in parser.json_ids
        }

    def example(self, number):
        return self.examples[f"authorization-example-{number}"]

    def json_example(self, number):
        return self.json_examples[f"authorization-example-{number}"]

    def token_form(self, number):
        headers, body = self.example(number).split("\n\n", 1)
        self.assertTrue(headers.startswith("POST /token HTTP/1.1\n"))
        self.assertIn("Content-Type: application/x-www-form-urlencoded", headers)
        fields = parse_qs(body.strip(), strict_parsing=True, keep_blank_values=True)
        for key, values in fields.items():
            self.assertEqual(len(values), 1, key)
            self.assertTrue(values[0], key)
        return {key: values[0] for key, values in fields.items()}

    def test_all_examples_are_present_and_json_is_valid(self):
        self.assertEqual(
            set(self.examples),
            {f"authorization-example-{number}" for number in range(1, 14)},
        )
        self.assertEqual(len(self.json_examples), 8)

    def test_metadata_digest_covers_exact_example_bytes(self):
        metadata = self.example(11)
        self.assertTrue(metadata.endswith("\n"))
        service = self.json_example(10)["service"][0]
        self.assertEqual(service["type"], "ANPOAuthClientMetadata")
        self.assertEqual(
            hashlib.sha256(metadata.encode("utf-8")).hexdigest(),
            service["anp_metadata_sha256"],
        )

    def test_did_fingerprint_matches_ed25519_multikey(self):
        document = self.json_example(10)
        multibase = document["verificationMethod"][0]["publicKeyMultibase"]
        self.assertTrue(multibase.startswith("z"))
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = 0
        for char in multibase[1:]:
            number = number * 58 + alphabet.index(char)
        decoded = number.to_bytes((number.bit_length() + 7) // 8, "big")
        self.assertEqual(decoded[:2], b"\xed\x01")
        self.assertEqual(len(decoded[2:]), 32)
        x = base64.urlsafe_b64encode(decoded[2:]).decode("ascii").rstrip("=")
        jwk = json.dumps(
            {"crv": "Ed25519", "kty": "OKP", "x": x},
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = base64.urlsafe_b64encode(hashlib.sha256(jwk.encode()).digest())
        self.assertEqual(
            document["id"].rsplit(":", 1)[1],
            "e1_" + fingerprint.decode("ascii").rstrip("="),
        )

    def test_hosted_client_identity_and_profile_are_consistent(self):
        header, assertion = self.json_example(2), self.json_example(3)
        document, metadata = self.json_example(10), self.json_example(11)
        client_id = document["id"]
        self.assertEqual(assertion["iss"], client_id)
        self.assertEqual(assertion["sub"], client_id)
        self.assertEqual(metadata["client_id"], client_id)
        self.assertEqual(header["kid"], document["verificationMethod"][0]["id"])
        self.assertIn(header["kid"], document["authentication"])
        self.assertEqual(
            metadata["anp_profile"], self.json_example(1)["anp_did_oauth"]["profile"]
        )
        self.assertEqual(metadata["token_endpoint_auth_method"], "private_key_jwt")
        request = self.token_form(4)
        self.assertEqual(request["client_id"], client_id)
        self.assertEqual(request["grant_type"], "client_credentials")
        self.assertEqual(
            request["client_assertion_type"],
            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        )

    def test_assertion_and_access_token_have_distinct_roles(self):
        assertion, token = self.json_example(3), self.json_example(12)
        self.assertEqual(assertion["aud"], self.json_example(1)["issuer"])
        self.assertGreater(assertion["exp"], assertion["iat"])
        self.assertLessEqual(assertion["exp"] - assertion["iat"], 300)
        self.assertEqual(token["iss"], assertion["aud"])
        self.assertEqual(token["client_id"], assertion["sub"])
        self.assertNotEqual(token["sub"], token["client_id"])
        self.assertEqual(token["aud"], self.json_example(9)["resource"])
        self.assertEqual(self.token_form(4)["resource"], token["aud"])

    def test_local_code_redemption_keeps_its_own_client_and_resource(self):
        request = self.token_form(13)
        self.assertEqual(request["grant_type"], "authorization_code")
        self.assertNotEqual(request["client_id"], self.json_example(11)["client_id"])
        self.assertEqual(request["resource"], self.json_example(9)["resource"])
        self.assertTrue(request["code"])
        self.assertTrue(request["code_verifier"])
        self.assertTrue(request["client_assertion"])
        redirect = urlparse(request["redirect_uri"])
        self.assertEqual(
            (redirect.scheme, redirect.hostname, redirect.port, redirect.path),
            ("http", "127.0.0.1", 49152, "/callback"),
        )
        self.assertFalse(redirect.query or redirect.fragment or redirect.username)


if __name__ == "__main__":
    unittest.main()
