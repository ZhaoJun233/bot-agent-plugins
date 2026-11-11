"""Small GitHub API client for trusted default-branch automation only."""
import base64
import json
import os
import re
import urllib.error
import urllib.request

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class GitHubError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


class GitHub:
    def __init__(self, repository, token=None):
        if not REPOSITORY.fullmatch(repository):
            raise ValueError("Invalid GitHub repository")
        self.repository = repository
        self.prefix = "/repos/" + repository
        self.token = token if token is not None else os.environ["GH_TOKEN"]
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, path, data=None, *, missing_ok=False):
        if not path.startswith(self.prefix + "/"):
            raise ValueError("API path must stay in the selected repository")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "Cache-Control": "no-cache",
                   "User-Agent": "bot-agent-marketplace", "Authorization": "Bearer " + self.token}
        body = None if data is None else json.dumps(data).encode("utf-8")
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request("https://api.github.com" + path, data=body, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            raise GitHubError("GitHub API HTTP " + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise GitHubError("GitHub API unavailable") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise GitHubError("GitHub API response exceeds limit")
        return json.loads(payload) if payload else None

    def get(self, suffix, **kwargs):
        return self.request("GET", self.prefix + suffix, **kwargs)

    def write(self, method, suffix, data):
        return self.request(method, self.prefix + suffix, data)

    def file(self, path, revision):
        if not SHA.fullmatch(revision) or path not in ("governance/ledger.json", "governance.json"):
            raise ValueError("Only fixed governance files may be read")
        result = self.get("/contents/" + path + "?ref=" + revision)
        if result.get("type") != "file" or result.get("encoding") != "base64" or result["size"] > 2 * 1024 * 1024:
            raise GitHubError("Invalid governance file response")
        content = base64.b64decode(result["content"].replace("\n", ""), validate=True)
        if len(content) != result["size"]:
            raise GitHubError("Governance file size mismatch")
        return content


def verify_pull_request(api, number, base_sha, candidate_sha):
    if type(number) is not int or number <= 0 or not SHA.fullmatch(base_sha) or not SHA.fullmatch(candidate_sha):
        raise ValueError("Expected PR number and exact base/candidate commits")
    pull = api.get("/pulls/" + str(number))
    if (pull["state"] != "open" or pull["base"]["repo"]["full_name"] != api.repository
            or pull["base"]["sha"] != base_sha or pull["head"]["sha"] != candidate_sha
            or pull["base"]["ref"] != pull["base"]["repo"]["default_branch"]):
        raise ValueError("Pull request changed; prepare and approve its current candidate")
    head_repository = pull["head"]["repo"]["full_name"]
    if not REPOSITORY.fullmatch(head_repository):
        raise ValueError("Invalid candidate repository")
    return pull
