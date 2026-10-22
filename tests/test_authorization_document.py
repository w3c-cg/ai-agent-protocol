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
OAUTH_PROFILE = "anp.authorization.oauth2.cimd.v1-draft1"


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

    def assert_cimd_url(self, value):
        url = urlparse(value)
        self.assertEqual(url.scheme, "https")
        self.assertTrue(url.hostname)
        self.assertTrue(url.path)
        self.assertFalse(url.query or url.fragment)
        self.assertIsNone(url.username)
        self.assertIsNone(url.password)
        self.assertFalse({".", ".."}.intersection(url.path.split("/")))

    def ed25519_jwk(self, method):
        """Decode the example's public Multikey; this is not a DID resolver."""
        self.assertEqual(method["type"], "Multikey")
        multibase = method["publicKeyMultibase"]
        self.assertTrue(multibase.startswith("z"))
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = 0
        for char in multibase[1:]:
            number = number * 58 + alphabet.index(char)
        decoded = number.to_bytes((number.bit_length() + 7) // 8, "big")
        self.assertEqual(decoded[:2], b"\xed\x01")
        self.assertEqual(len(decoded[2:]), 32)
        x = base64.urlsafe_b64encode(decoded[2:]).decode("ascii").rstrip("=")
        return {"crv": "Ed25519", "kty": "OKP", "x": x}

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
        self.assertEqual(service["type"], "ANPCIMD")
        self.assertRegex(service["anp_metadata_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            hashlib.sha256(metadata.encode("utf-8")).hexdigest(),
            service["anp_metadata_sha256"],
        )
        # The embedded key and final LF are part of the authenticated bytes.
        x = self.json_example(11)["jwks"]["keys"][0]["x"]
        variants = (
            ("without final LF", metadata[:-1]),
            ("changed signing key", metadata.replace(x, "A" * len(x), 1)),
        )
        for name, changed in variants:
            with self.subTest(variant=name):
                self.assertNotEqual(changed, metadata)
                self.assertNotEqual(
                    hashlib.sha256(changed.encode("utf-8")).hexdigest(),
                    service["anp_metadata_sha256"],
                )

    def test_did_fingerprint_matches_ed25519_multikey(self):
        document = self.json_example(10)
        jwk = json.dumps(
            self.ed25519_jwk(document["verificationMethod"][0]),
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = base64.urlsafe_b64encode(hashlib.sha256(jwk.encode()).digest())
        self.assertEqual(
            document["id"].rsplit(":", 1)[1],
            "e1_" + fingerprint.decode("ascii").rstrip("="),
        )

    def test_hosted_client_identity_and_profile_are_consistent(self):
        assertion = self.json_example(3)
        authorization_server = self.json_example(1)
        document, metadata = self.json_example(10), self.json_example(11)
        client_id = metadata["client_id"]
        self.assert_cimd_url(client_id)
        self.assertNotEqual(client_id, document["id"])
        self.assertEqual(assertion["iss"], client_id)
        self.assertEqual(assertion["sub"], client_id)
        services = [item for item in document["service"] if item["type"] == "ANPCIMD"]
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0]["id"], document["id"] + "#oauth-client")
        self.assertEqual(services[0]["serviceEndpoint"], client_id)
        # This example includes the optional reverse-discovery hint.
        self.assertEqual(metadata["anp_did"], document["id"])
        self.assertIs(authorization_server["client_id_metadata_document_supported"], True)
        binding = authorization_server["anp_cimd_binding"]
        self.assertEqual(binding["profile"], OAUTH_PROFILE)
        self.assertIn("did:wba", binding["did_methods_supported"])
        self.assertIn("self_published", binding["client_enrollment_methods_supported"])
        self.assertEqual(
            set(binding["redirect_uri_modes_supported"]), {"https", "loopback"}
        )
        self.assertNotIn("anp_did_oauth", authorization_server)
        for field in ("anp_profile", "anp_application_type", "client_secret"):
            self.assertNotIn(field, metadata)
        self.assertEqual(metadata["token_endpoint_auth_method"], "private_key_jwt")
        self.assertIn(
            "private_key_jwt", authorization_server["token_endpoint_auth_methods_supported"]
        )
        request = self.token_form(4)
        self.assertEqual(request["client_id"], client_id)
        self.assertEqual(request["grant_type"], "client_credentials")
        self.assertEqual(
            request["client_assertion_type"],
            "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        )

    def test_assertion_signing_key_is_authorized_and_matches_jwks(self):
        header = self.json_example(2)
        document, metadata = self.json_example(10), self.json_example(11)
        service = document["service"][0]
        self.assertNotIn("jwks_uri", metadata)  # The example uses embedded JWKS.
        signing_keys = [
            key for key in metadata["jwks"]["keys"] if key["kid"] == header["kid"]
        ]
        self.assertEqual(
            len(signing_keys), 1, "The assertion must select an unambiguous key"
        )
        signing_key = signing_keys[0]
        self.assertNotIn("d", signing_key)
        self.assertEqual(signing_key["use"], "sig")
        self.assertEqual(signing_key["alg"], header["alg"])
        self.assertEqual(metadata["token_endpoint_auth_signing_alg"], header["alg"])
        self.assertIn(
            header["alg"],
            self.json_example(1)["token_endpoint_auth_signing_alg_values_supported"],
        )
        for field in ("jwk", "jku", "x5u", "x5c"):
            self.assertNotIn(field, header)

        authorized = service["anp_oauth_keys"]
        self.assertTrue(authorized)
        self.assertEqual(len(authorized), len(set(authorized)))
        methods = {method["id"]: method for method in document["verificationMethod"]}
        self.assertEqual(len(methods), len(document["verificationMethod"]))
        authorized_public_keys = []
        for key_id in authorized:
            self.assertIn(key_id, document["authentication"])
            self.assertTrue(key_id.startswith(document["id"] + "#"))
            self.assertTrue(key_id.split("#", 1)[1])
            self.assertIn(key_id, methods)
            self.assertEqual(methods[key_id]["controller"], document["id"])
            authorized_public_keys.append(self.ed25519_jwk(methods[key_id]))
        # A DID-shaped kid is only a label: compare the actual public-key bytes.
        selected_public_key = {
            field: signing_key[field] for field in ("crv", "kty", "x")
        }
        self.assertIn(selected_public_key, authorized_public_keys)
        context_terms = {
            term for context in document["@context"] if isinstance(context, dict)
            for term in context
        }
        self.assertTrue(
            {"ANPCIMD", "anp_oauth_keys", "anp_metadata_sha256"} <= context_terms
        )

    def test_assertion_and_access_token_have_distinct_roles(self):
        assertion, token = self.json_example(3), self.json_example(12)
        self.assertEqual(self.json_example(2)["typ"], "JWT")
        self.assertEqual(assertion["aud"], self.json_example(1)["issuer"])
        self.assertIs(type(assertion["iat"]), int)
        self.assertIs(type(assertion["exp"]), int)
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
        self.assert_cimd_url(request["client_id"])
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
