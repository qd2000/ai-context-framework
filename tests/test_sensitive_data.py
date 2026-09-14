from __future__ import annotations

import json
import unittest

from ai_context_framework.sensitive_data import (
    credential_key_action,
    contains_credential_like_text,
    redact_credential_like_text,
    sanitize_public_payload,
)


class SensitiveDataTests(unittest.TestCase):
    def test_public_metadata_is_not_classified_by_entropy_or_identifier_shape(self) -> None:
        digest = "d" * 64
        values = {
            "lease_id": "7da49016-80ff-42de-a1d7-f223c15f6fe2",
            "generation": 91,
            "git_sha": "a" * 40,
            "digest": digest,
            "external_id": "runtime-job-123",
        }
        self.assertFalse(any(contains_credential_like_text(value) for value in values.values()))
        self.assertEqual(values, sanitize_public_payload(values))

    def test_plain_token_and_license_labels_are_not_secrets_by_name_alone(self) -> None:
        values = {
            "token": "page-2",
            "license": "MIT",
            "pagination_token": "next-page-marker",
            "paginationToken": "next-page-camel",
            "continuation_token": "continuation-marker",
        }
        self.assertFalse(contains_credential_like_text("token=page-2"))
        self.assertFalse(contains_credential_like_text("license=MIT"))
        self.assertFalse(contains_credential_like_text("paginationToken=next-page-camel"))
        self.assertFalse(contains_credential_like_text("continuation_token=continuation-marker"))
        self.assertEqual(values, sanitize_public_payload(values))

    def test_named_provider_tokens_are_explicit_credentials_but_generic_tokens_remain_public(self) -> None:
        provider_values = {
            "AUTH_TOKEN": "auth-secret-sentinel",
            "ID_TOKEN": "id-secret-sentinel",
            "SERVICE_ACCOUNT_TOKEN": "service-account-secret-sentinel",
            "CI_JOB_TOKEN": "ci-job-secret-sentinel",
            "GH_TOKEN": "gh-secret-sentinel",
            "NODE_AUTH_TOKEN": "node-auth-secret-sentinel",
            "GITHUB_TOKEN": "provider-one",
            "NPM_TOKEN": "provider-two",
            "AWS_SESSION_TOKEN": "provider-three",
            "VAULT_TOKEN": "provider-four",
        }
        cleaned = sanitize_public_payload(provider_values)
        self.assertEqual({key: "[redacted]" for key in provider_values}, cleaned)

        text = " ".join(f"{key}={value}" for key, value in provider_values.items())
        redacted, count = redact_credential_like_text(text)
        self.assertEqual(len(provider_values), count)
        for value in provider_values.values():
            self.assertNotIn(value, redacted)

        public = "token=page-2 paginationToken=next-page license=MIT continuation_token=resume-7"
        preserved, count = redact_credential_like_text(public)
        self.assertEqual(0, count)
        self.assertEqual(public, preserved)

    def test_fail_closed_text_forms_cover_cli_suffixes_incomplete_private_key_and_authorization_once(self) -> None:
        cases = (
            ("--api-key=flag-secret-sentinel", "flag-secret-sentinel"),
            ("--password space-secret-sentinel", "space-secret-sentinel"),
            ("password=alpha,beta-secret-sentinel", "beta-secret-sentinel"),
            (
                "-----BEGIN PRIVATE KEY-----\nincomplete-private-sentinel",
                "incomplete-private-sentinel",
            ),
        )
        for raw, sentinel in cases:
            with self.subTest(raw=raw):
                cleaned, count = redact_credential_like_text(raw)
                self.assertGreaterEqual(count, 1)
                self.assertNotIn(sentinel, cleaned)

        authorization, count = redact_credential_like_text(
            "Authorization=Bearer bearer-secret-sentinel"
        )
        self.assertEqual(1, count)
        self.assertEqual(
            "Authorization=[redacted credential-like value]",
            authorization,
        )
        self.assertNotIn("bearer-secret-sentinel", authorization)

        public = "token=page-2 license=MIT pagination_token=next-page short=ok"
        cleaned, count = redact_credential_like_text(public)
        self.assertEqual(0, count)
        self.assertEqual(public, cleaned)

    def test_explicit_auth_token_names_share_one_semantic_classifier(self) -> None:
        for key in (
            "AUTH_TOKEN",
            "ID_TOKEN",
            "SERVICE_ACCOUNT_TOKEN",
            "CI_JOB_TOKEN",
            "GH_TOKEN",
            "NODE_AUTH_TOKEN",
        ):
            with self.subTest(key=key):
                self.assertEqual("redact", credential_key_action(key))
        for key in (
            "token",
            "pagination_token",
            "continuation_token",
            "license",
            "digest",
            "job_id",
        ):
            with self.subTest(key=key):
                self.assertIsNone(credential_key_action(key))

    def test_explicit_provider_tokens_share_structured_and_text_classification(self) -> None:
        provider_values = {
            "GITHUB_TOKEN": "github-secret-sentinel",
            "NPM_TOKEN": "npm-secret-sentinel",
            "AWS_SESSION_TOKEN": "aws-secret-sentinel",
            "VAULT_TOKEN": "vault-secret-sentinel",
            "CI_GITLAB_TOKEN": "gitlab-secret-sentinel",
        }
        cleaned = sanitize_public_payload(provider_values)
        self.assertEqual(
            {key: "[redacted]" for key in provider_values},
            cleaned,
        )
        text = " ".join(f"{key}={value}" for key, value in provider_values.items())
        redacted, count = redact_credential_like_text(text)
        self.assertEqual(len(provider_values), count)
        for sentinel in provider_values.values():
            self.assertNotIn(sentinel, redacted)

        public_text = "token=page-2 paginationToken=next-page license=MIT continuation_token=resume-7"
        preserved, count = redact_credential_like_text(public_text)
        self.assertEqual(0, count)
        self.assertEqual(public_text, preserved)

    def test_explicit_structured_credential_keys_are_redacted_without_hiding_plain_token_license(self) -> None:
        payload = {
            "client_secret": "client-value",
            "secret_key": "key-value",
            "authorization": "Bearer bearer-value",
            "bearer_token": "bearer-value",
            "token": "page-2",
            "license": "MIT",
            "pagination_token": "next-page-marker",
            "digest": "d" * 64,
            "job_id": "runtime-job-123",
        }
        cleaned = sanitize_public_payload(payload)
        for key in ("client_secret", "secret_key", "authorization", "bearer_token"):
            self.assertEqual("[redacted]", cleaned[key])
        self.assertEqual("page-2", cleaned["token"])
        self.assertEqual("MIT", cleaned["license"])
        self.assertEqual("next-page-marker", cleaned["pagination_token"])
        self.assertEqual("d" * 64, cleaned["digest"])
        self.assertEqual("runtime-job-123", cleaned["job_id"])

    def test_camel_and_namespaced_credential_keys_share_semantic_classifier(self) -> None:
        payload = {
            "clientSecret": "camel-client-sentinel",
            "apiKey": "camel-api-sentinel",
            "apiSecret": "camel-api-secret-sentinel",
            "accessToken": "camel-access-sentinel",
            "refreshToken": "camel-refresh-sentinel",
            "bearerToken": "camel-bearer-sentinel",
            "privateKey": "camel-private-sentinel",
            "secretKey": "camel-secret-key-sentinel",
            "fenceToken": "camel-fence-sentinel",
            "fenceTokenHash": "camel-verifier-sentinel",
            "OPENAI_API_KEY": "prefixed-api-sentinel",
            "DATABASE_PASSWORD": "prefixed-password-sentinel",
            "AWS_SECRET_ACCESS_KEY": "prefixed-aws-sentinel",
            "X-API-Key": "header-api-sentinel",
            "token": "page-2",
            "license": "MIT",
            "paginationToken": "next-page-marker",
        }
        cleaned = sanitize_public_payload(payload)
        for key in (
            "clientSecret",
            "apiKey",
            "apiSecret",
            "accessToken",
            "refreshToken",
            "bearerToken",
            "privateKey",
            "secretKey",
            "OPENAI_API_KEY",
            "DATABASE_PASSWORD",
            "AWS_SECRET_ACCESS_KEY",
            "X-API-Key",
        ):
            self.assertEqual("[redacted]", cleaned[key])
        self.assertNotIn("fenceToken", cleaned)
        self.assertNotIn("fenceTokenHash", cleaned)
        self.assertEqual("page-2", cleaned["token"])
        self.assertEqual("MIT", cleaned["license"])
        self.assertEqual("next-page-marker", cleaned["paginationToken"])
        self.assertEqual("redact", credential_key_action("clientSecret"))
        self.assertEqual("redact", credential_key_action("AWS_SECRET_ACCESS_KEY"))
        self.assertEqual("omit", credential_key_action("fenceTokenHash"))
        self.assertIsNone(credential_key_action("paginationToken"))

    def test_text_redaction_covers_json_python_repr_and_yaml_credential_assignments(self) -> None:
        sentinels = {
            "json-client": "client-secret-json",
            "json-api": "api-secret-json",
            "repr-secret": "secret-key-repr",
            "yaml-bearer": "bearer-token-yaml",
        }
        value = "\n".join(
            [
                json.dumps(
                    {
                        "client_secret": sentinels["json-client"],
                        "api_key": sentinels["json-api"],
                        "token": "page-2",
                    }
                ),
                repr({"secret_key": sentinels["repr-secret"], "license": "MIT"}),
                f"bearer_token: {sentinels['yaml-bearer']}",
                "token=page-2",
                "license=MIT",
            ]
        )
        cleaned, count = redact_credential_like_text(value)
        self.assertGreaterEqual(count, 4)
        for sentinel in sentinels.values():
            self.assertNotIn(sentinel, cleaned)
        self.assertIn('"token": "page-2"', cleaned)
        self.assertIn("'license': 'MIT'", cleaned)
        self.assertIn("token=page-2", cleaned)
        self.assertIn("license=MIT", cleaned)

    def test_prefixed_and_camel_assignment_text_is_redacted_without_generic_token_false_positive(self) -> None:
        value = " ".join(
            [
                "OPENAI_API_KEY=prefix-api-sentinel",
                "DATABASE_PASSWORD=prefix-password-sentinel",
                "AWS_SECRET_ACCESS_KEY=prefix-aws-sentinel",
                "X-API-Key=header-api-sentinel",
                "clientSecret=camel-client-sentinel",
                "apiSecret=camel-api-secret-sentinel",
                "bearerToken=camel-bearer-sentinel",
                "token=page-2",
                "license=MIT",
                "paginationToken=next-page-marker",
            ]
        )
        cleaned, count = redact_credential_like_text(value)
        self.assertGreaterEqual(count, 7)
        for sentinel in (
            "prefix-api-sentinel",
            "prefix-password-sentinel",
            "prefix-aws-sentinel",
            "header-api-sentinel",
            "camel-client-sentinel",
            "camel-api-secret-sentinel",
            "camel-bearer-sentinel",
        ):
            self.assertNotIn(sentinel, cleaned)
        self.assertIn("token=page-2", cleaned)
        self.assertIn("license=MIT", cleaned)
        self.assertIn("paginationToken=next-page-marker", cleaned)

    def test_public_payload_omits_owner_auth_material_and_redacts_explicit_secrets(self) -> None:
        payload = {
            "lease": {
                "fence_token": "raw-owner-authentication-material",
                "fence_token_hash": "verifier-not-needed-publicly",
                "lease_id": "lease-public",
            },
            "password": "password-value",
            "diagnostic": "request failed with api_key=service-secret",
        }
        cleaned = sanitize_public_payload(payload)
        self.assertEqual(
            {
                "lease": {"lease_id": "lease-public"},
                "password": "[redacted]",
                "diagnostic": "request failed with api_key=[redacted credential-like value]",
            },
            cleaned,
        )

    def test_text_redaction_covers_private_keys_authorization_and_openai_style_keys(self) -> None:
        value = (
            "Authorization: Bearer bearer-secret\n"
            "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n"
            "sk-abcdefghijklmnopqrstuvwxyz123456"
        )
        cleaned, count = redact_credential_like_text(value)
        self.assertGreaterEqual(count, 3)
        self.assertNotIn("bearer-secret", cleaned)
        self.assertNotIn("BEGIN PRIVATE KEY", cleaned)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", cleaned)


if __name__ == "__main__":
    unittest.main()
