import csv
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import dashboard_server as dashboard_module
from dashboard_server import (
    AuthManager, JobManager, origin_is_allowed, parse_progress_line, password_matches, password_record,
    read_results, validate_job_payload, validate_client_id,
)


class DashboardTest(unittest.TestCase):
    def test_validate_job(self):
        job = validate_job_payload({"query": "restaurants in Nanded", "max_results": 25})
        self.assertEqual(job["max_results"], 25)

    def test_maximum_result_limit_is_2000(self):
        job = validate_job_payload({"query": "restaurants in Nanded", "max_results": 2000})
        self.assertEqual(job["max_results"], 2000)
        with self.assertRaisesRegex(ValueError, "Maximum results"):
            validate_job_payload({"query": "restaurants in Nanded", "max_results": 2001})
        self.assertEqual(job["enrichment"], "website")

    def test_reject_empty_query(self):
        with self.assertRaises(ValueError):
            validate_job_payload({"query": "  "})

    def test_progress_parser(self):
        progress = parse_progress_line("Discovery progress: 8/20 listing URL(s)", {})
        self.assertEqual(progress["discovered"], 8)
        progress = parse_progress_line("[3/8] Reading Google listing...", progress)
        self.assertEqual(progress["current"], 3)
        progress = parse_progress_line("Checkpoint saved (2 record(s)): output.xlsx", progress)
        self.assertEqual(progress["records"], 2)

    def test_csv_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["business_name", "phone"])
                writer.writeheader()
                writer.writerow({"business_name": "Demo Cafe", "phone": "123"})
            result = read_results(path)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["rows"][0]["business_name"], "Demo Cafe")

    def test_password_hash_is_salted(self):
        first = password_record("Secure123")
        second = password_record("Secure123")
        self.assertNotEqual(first["salt"], second["salt"])
        self.assertTrue(password_matches("Secure123", first))
        self.assertFalse(password_matches("Wrong123", first))

    def test_admin_setup_login_logout_and_password_change(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = AuthManager(Path(directory) / "admin.json", bootstrap_from_env=False)
            self.assertTrue(auth.setup_required)
            token, user = auth.setup("Prathmesh Dake", "Admin@Example.com", "Secure123")
            self.assertEqual(user["email"], "admin@example.com")
            self.assertIsNotNone(auth.session_user(token))
            auth.logout(token)
            self.assertIsNone(auth.session_user(token))
            token, _ = auth.login("admin@example.com", "Secure123", "test-client")
            auth.change_password(token, "Secure123", "Updated456")
            self.assertIsNotNone(auth.session_user(token))
            with self.assertRaises(PermissionError):
                auth.login("admin@example.com", "Secure123", "old-password")
            new_token, _ = auth.login("admin@example.com", "Updated456", "new-password")
            self.assertIsNotNone(auth.session_user(new_token))

    def test_bootstrap_admin_from_environment(self):
        variables = {
            "ITCYBER_BOOTSTRAP_ADMIN_NAME": "Prathmesh Dake",
            "ITCYBER_BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
            "ITCYBER_BOOTSTRAP_ADMIN_PASSWORD": "Secure123",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", variables, clear=False):
            auth = AuthManager(Path(directory) / "admin.json")
            self.assertFalse(auth.setup_required)
            token, user = auth.login("admin@example.com", "Secure123", "bootstrap-test")
            self.assertEqual(user["name"], "Prathmesh Dake")
            self.assertIsNotNone(auth.session_user(token))

    def test_device_id_validation(self):
        value = validate_client_id("11111111-1111-4111-8111-111111111111")
        self.assertEqual(value, "11111111-1111-4111-8111-111111111111")
        with self.assertRaises(ValueError):
            validate_client_id("short")

    def test_job_manager_filters_jobs_by_device(self):
        with tempfile.TemporaryDirectory() as directory:
            data_root = Path(directory) / "data"
            output_root = Path(directory) / "output"
            history = data_root / "jobs.json"
            with patch.multiple(
                dashboard_module, DATA_ROOT=data_root, OUTPUT_ROOT=output_root, HISTORY_FILE=history
            ):
                manager = JobManager()
                base = {
                    "query": "demo", "status": "completed", "created_at": "2026-08-19T10:00:00+05:30",
                    "output_file": "", "logs": [], "progress": {},
                }
                manager.jobs = {
                    "job-a": {"id": "job-a", "client_id": "device-A-1234567890", **deepcopy(base)},
                    "job-b": {"id": "job-b", "client_id": "device-B-1234567890", **deepcopy(base)},
                    "legacy": {"id": "legacy", **deepcopy(base)},
                }
                jobs_a = manager.list("device-A-1234567890")
                self.assertEqual([job["id"] for job in jobs_a], ["job-a"])
                self.assertIsNotNone(manager.get("job-a", "device-A-1234567890"))
                self.assertIsNone(manager.get("job-b", "device-A-1234567890"))
                self.assertNotIn("client_id", jobs_a[0])

    def test_cors_origin_matching(self):
        with patch.dict("os.environ", {"ITCYBER_ALLOWED_ORIGINS": "https://itcyber.vercel.app,https://*.example.com"}):
            self.assertTrue(origin_is_allowed("https://itcyber.vercel.app"))
            self.assertTrue(origin_is_allowed("https://preview.example.com"))
            self.assertFalse(origin_is_allowed("https://attacker.invalid"))


if __name__ == "__main__":
    unittest.main()
