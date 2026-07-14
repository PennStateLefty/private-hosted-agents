#!/usr/bin/env python3
"""G7 — APIM AI Gateway governance proof.

Proves, three consecutive times, that the APIM GenAI gateway in front of the private
Foundry account enforces a token-per-minute limit (returns HTTP 429 with rate-limit
headers when the estimated request exceeds the budget) and that restoring a sane
budget lets governed traffic flow (HTTP 200 completion via managed-identity auth to
the private backend — no keys).

Each run:
  1. ENFORCE  — set tokens-per-minute low, send a large prompt -> expect 429 +
     x-ratelimit-remaining-tokens + "Token limit" message.
  2. RESTORE  — set tokens-per-minute high, send a small prompt -> expect 200 with a
     completion (governance no longer blocking; backend reached privately).

Bounded retries absorb transient 5xx / propagation. End state leaves the policy at the
restored (production-sane) budget. Writes evidence/g7-gateway-run{1,2,3}.json.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import subprocess
import sys
import time

SUB = "987a5b92-2573-4981-a76c-bbd7756592c8"
RG = "rg-pha-dev"
APIM = "apim-pha-dev"
GATEWAY_HOST = "apim-pha-dev.azure-api.net"
GATEWAY = f"https://{GATEWAY_HOST}"
DEPLOYMENT = "chat"
API_VERSION = "2025-01-01-preview"
ENFORCE_TPM = 100
RESTORE_TPM = 20000
RUNS = 3
KEY_FILE = "/tmp/apim-key.txt"

# When APIM public network access is Disabled, the gateway is only reachable via its
# private endpoint IP inside the spoke VNet (over the P2S VPN). The macOS resolver may
# still hand curl/urllib the public A record, so we pin the connection to the private
# endpoint IP while preserving SNI/Host = the real gateway hostname. Set APIM_PRIVATE_IP
# to "" to use normal DNS resolution (public path).
PRIVATE_IP = os.environ.get("APIM_PRIVATE_IP", "192.168.2.26")


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPSConnection that dials a fixed IP but keeps SNI/Host as the real hostname."""

    def connect(self) -> None:
        sock = socket.create_connection((PRIVATE_IP, self.port or 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)

API_BASE = (
    f"https://management.azure.com/subscriptions/{SUB}/resourceGroups/{RG}"
    f"/providers/Microsoft.ApiManagement/service/{APIM}"
)

POLICY_TMPL = (
    '<policies><inbound><base />'
    '<authentication-managed-identity resource="https://cognitiveservices.azure.com" '
    'output-token-variable-name="msi-access-token" ignore-error="false" />'
    '<set-header name="Authorization" exists-action="override">'
    '<value>@("Bearer " + (string)context.Variables["msi-access-token"])</value></set-header>'
    '<azure-openai-token-limit counter-key="@(context.Subscription.Id)" '
    'tokens-per-minute="{tpm}" estimate-prompt-tokens="true" '
    'remaining-tokens-header-name="x-ratelimit-remaining-tokens" '
    'tokens-consumed-header-name="x-tokens-consumed" />'
    '<azure-openai-emit-token-metric namespace="genai">'
    '<dimension name="subscription-id" value="@(context.Subscription.Id)" /></azure-openai-emit-token-metric>'
    '</inbound><backend><base /></backend><outbound><base /></outbound>'
    '<on-error><base /></on-error></policies>'
)


def _key() -> str:
    with open(KEY_FILE) as fh:
        return fh.read().strip()


def set_tpm(tpm: int) -> None:
    body = json.dumps({"properties": {"format": "rawxml", "value": POLICY_TMPL.format(tpm=tpm)}})
    with open("/tmp/g7-policy.json", "w") as fh:
        fh.write(body)
    url = f"{API_BASE}/apis/azure-openai/policies/policy?api-version=2023-05-01-preview"
    r = subprocess.run(
        ["az", "rest", "--method", "put", "--url", url, "--body", "@/tmp/g7-policy.json", "-o", "none"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"policy set failed: {r.stderr[-300:]}")
    time.sleep(8)  # propagation


def enforce_call(prompt: str, tpm_probes: int = 6):
    """Send the large prompt, tolerating policy-propagation lag.

    Right after lowering tokens-per-minute the gateway may still serve a few requests
    on the previous (higher) budget. Re-send with bounded backoff until the new low
    budget takes effect (HTTP 429) or probes are exhausted.
    """
    status = headers = body = None
    for i in range(tpm_probes):
        status, headers, body = call(prompt, max_tokens=16)
        if status == 429:
            return status, headers, body
        time.sleep(4)  # let the lowered policy propagate, then re-probe
    return status, headers, body


def call(prompt: str, max_tokens: int = 16, attempts: int = 4):
    path = f"/openai/deployments/{DEPLOYMENT}/chat/completions?api-version={API_VERSION}"
    body = json.dumps({"messages": [{"role": "user", "content": prompt}], "max_completion_tokens": max_tokens}).encode()
    headers = {"Ocp-Apim-Subscription-Key": _key(), "Content-Type": "application/json"}
    ctx = ssl.create_default_context()
    last = None
    for i in range(attempts):
        try:
            if PRIVATE_IP:
                conn = _PinnedHTTPSConnection(GATEWAY_HOST, 443, timeout=60, context=ctx)
            else:
                conn = http.client.HTTPSConnection(GATEWAY_HOST, 443, timeout=60, context=ctx)
            try:
                conn.request("POST", path, body=body, headers=headers)
                resp = conn.getresponse()
                status = resp.status
                rheaders = {k.lower(): v for k, v in resp.getheaders()}
                text = resp.read().decode()
            finally:
                conn.close()
            # 429 is an expected, terminal outcome for the enforce phase — return it.
            if status == 429:
                return status, rheaders, text
            if status >= 500:
                last = (status, rheaders, text)
                time.sleep(2 * (i + 1))
                continue
            return status, rheaders, text
        except Exception as e:  # transient network
            last = (0, {}, str(e))
            time.sleep(2 * (i + 1))
    return last


def run_once(n: int) -> dict:
    big_prompt = "Please summarize the following workshop agenda in detail. " * 60
    # ENFORCE
    set_tpm(ENFORCE_TPM)
    e_status, e_headers, e_body = enforce_call(big_prompt)
    enforce_ok = (
        e_status == 429
        and "x-ratelimit-remaining-tokens" in {k.lower() for k in e_headers}
        and "token limit" in e_body.lower()
    )
    # RESTORE
    set_tpm(RESTORE_TPM)
    r_status, r_headers, r_body = call("Say hello in exactly 3 words.", max_tokens=16)
    completion = None
    try:
        completion = json.loads(r_body)["choices"][0]["message"]["content"]
    except Exception:
        pass
    restore_ok = r_status == 200 and bool(completion)

    try:
        _emsg = json.loads(e_body).get("message") if e_body.strip().startswith("{") else e_body
    except Exception:
        _emsg = e_body
    _emsg = (_emsg or "")[:160]
    result = {
        "run": n,
        "enforce": {
            "tpm": ENFORCE_TPM,
            "status": e_status,
            "remaining_tokens": e_headers.get("x-ratelimit-remaining-tokens"),
            "retry_after": e_headers.get("retry-after"),
            "message": _emsg,
            "ok": enforce_ok,
        },
        "restore": {
            "tpm": RESTORE_TPM,
            "status": r_status,
            "remaining_tokens": r_headers.get("x-ratelimit-remaining-tokens"),
            "completion": completion,
            "ok": restore_ok,
        },
        "pass": enforce_ok and restore_ok,
    }
    return result


def main() -> int:
    os.makedirs("evidence", exist_ok=True)
    results = []
    for n in range(1, RUNS + 1):
        res = run_once(n)
        results.append(res)
        path = f"evidence/g7-gateway-run{n}.json"
        with open(path, "w") as fh:
            json.dump(res, fh, indent=2)
        e, r = res["enforce"], res["restore"]
        print(
            f"run{n}: ENFORCE tpm={e['tpm']} -> HTTP {e['status']} "
            f"(remaining={e['remaining_tokens']}) | RESTORE tpm={r['tpm']} -> HTTP {r['status']} "
            f"completion={r['completion']!r} | {'PASS' if res['pass'] else 'FAIL'}"
        )
    # Leave gateway at restored budget.
    set_tpm(RESTORE_TPM)
    passed = sum(1 for r in results if r["pass"])
    print(f"\nG7 governance: {passed}/{RUNS} consecutive PASS (end state: tpm={RESTORE_TPM})")
    return 0 if passed == RUNS else 1


if __name__ == "__main__":
    sys.exit(main())
