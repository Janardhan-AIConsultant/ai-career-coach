from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Testimonial, User
from tests.guest_fixtures import Env

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "seed_sample_testimonials.py"


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("seed_sample", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_samples_are_labelled_public_idempotent_and_removable(env: Env) -> None:
    mod = _load()
    assert mod.add(env.db) == 3
    assert mod.add(env.db) == 0  # idempotent
    rows = env.db.scalars(select(Testimonial)).all()
    assert len(rows) == 3 and all("(demo)" in (t.display_name or "") for t in rows)
    shown = env.client.get("/api/v1/testimonials/public").json()
    assert len(shown) == 3 and all("sample" in t["display_name"].lower() for t in shown)
    sample = env.db.scalar(select(User).where(User.email == mod.SAMPLE_EMAIL))
    assert sample is not None and sample.is_active is False  # nobody can sign in as the sample account
    assert mod.remove(env.db) == 3
    assert env.db.scalars(select(Testimonial)).all() == []
    assert env.client.get("/api/v1/testimonials/public").json() == []


def test_script_refuses_to_run_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()

    class Prod:
        app_env = "production"

    monkeypatch.setattr(mod, "get_settings", lambda: Prod())
    assert mod.main(["seed"]) == 2
