import json
from pathlib import Path

def test_course_catalog():
    p=Path(__file__).parents[1]/"content"/"cpp_beginner.json"
    data=json.loads(p.read_text(encoding="utf-8"))
    assert len(data)==13
    assert all("title" in x and "objective" in x for x in data.values())

def test_security_limiter():
    from app.security.limits import RateLimiter
    r=RateLimiter(2,60)
    assert r.allow("u") and r.allow("u") and not r.allow("u")

def test_content_limits():
    from app.security.limits import clamp_text
    assert clamp_text("abcdef",3)=="abc"
