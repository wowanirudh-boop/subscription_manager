import json
import stat
from urllib.parse import parse_qs, urlparse

from srt_phase0 import auth


def test_start_builds_readonly_pkce_url(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    url = auth.start("me@gmail.com", tmp_path)
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]  # D8: nothing else
    assert q["redirect_uri"] == [auth.REDIRECT_URI]
    assert q["access_type"] == ["offline"] and q["code_challenge_method"] == ["S256"]
    pending = tmp_path / "pending-me_at_gmail.com.json"
    assert stat.S_IMODE(pending.stat().st_mode) == 0o600
    assert set(json.loads(pending.read_text())) == {"state", "verifier"}
