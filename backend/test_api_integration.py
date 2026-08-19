import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FRONTEND_ORIGIN = "https://frontend.example"
CLIENT_ID = "11111111-1111-4111-8111-111111111111"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ApiIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.port = free_port()
        root = Path(self.temporary.name)
        env = os.environ.copy()
        env.update({
            "ITCYBER_DATA_DIR": str(root / "dashboard_data"),
            "ITCYBER_OUTPUT_DIR": str(root / "output"),
            "ITCYBER_BROWSER_PROFILE_DIR": str(root / "browser_profile"),
            "ITCYBER_ALLOWED_ORIGINS": FRONTEND_ORIGIN,
        })
        self.process = subprocess.Popen(
            [sys.executable, "-u", "dashboard_server.py", "--host", "127.0.0.1", "--port", str(self.port), "--no-open"],
            cwd=Path(__file__).parent,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                status, body, _ = self.request("/api/health")
                if status == 200 and body.get("ok"):
                    return
            except (HTTPError, URLError, ConnectionError):
                time.sleep(0.1)
        output = self.process.stdout.read() if self.process.stdout else ""
        self.fail(f"Backend did not become healthy.\n{output}")

    def tearDown(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.process.stdout:
            self.process.stdout.close()
        self.temporary.cleanup()

    def request(self, path, method="GET", payload=None, token="", origin=FRONTEND_ORIGIN, client_id=CLIENT_ID):
        headers = {"Origin": origin}
        if client_id:
            headers["X-Client-ID"] = client_id
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                raw = response.read()
                body = json.loads(raw) if raw else {}
                return response.status, body, response.headers
        except HTTPError as error:
            raw = error.read()
            body = json.loads(raw) if raw else {}
            return error.code, body, error.headers

    def test_health_direct_jobs_and_cors(self):
        status, health, headers = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["cloud_ready"])
        self.assertFalse(health["auth_required"])
        self.assertFalse(health["setup_required"])
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), FRONTEND_ORIGIN)

        status, auth, _ = self.request("/api/auth/status")
        self.assertEqual(status, 200)
        self.assertTrue(auth["authenticated"])
        self.assertTrue(auth["auth_disabled"])

        status, jobs, _ = self.request("/api/jobs")
        self.assertEqual(status, 200)
        self.assertEqual(jobs["jobs"], [])

        status, missing_device, _ = self.request("/api/jobs", client_id="")
        self.assertEqual(status, 400)
        self.assertIn("device session", missing_device["error"].lower())

        status, blocked, _ = self.request("/api/health", origin="https://attacker.invalid")
        self.assertEqual(status, 403)
        self.assertIn("not allowed", blocked["error"].lower())


if __name__ == "__main__":
    unittest.main()
