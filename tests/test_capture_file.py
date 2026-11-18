"""`amperstand capture-file`: extract audio with ffmpeg, upload it, follow the server's transcription job."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from amperstand import cli, media

BASE = "http://vault.test"
JOB = "1794921265-0b77719c"
SUBMIT = re.compile(rf"{BASE}/transcribe/jobs\?.*")
STATUS = f"{BASE}/transcribe/jobs/{JOB}"

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def test_title_from_filename():
    assert media.title_from_filename(Path("riverside_ai_seo_almas_youtube (1).mp4")) == "riverside ai seo almas youtube"
    assert media.title_from_filename(Path("Team sync.m4a")) == "Team sync"


def test_hms():
    assert media.hms(8585.4) == "2:23:05" and media.hms(59) == "0:00:59"


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    """25 s of tone with a video track."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    out = tmp_path / "Weekly_demo (2).mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=25",
         "-f", "lavfi", "-i", "color=c=black:s=64x64:d=25", "-shortest", str(out)],
        check=True,
    )
    return out


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AMPERSTAND_API_KEY", "devkey")
    monkeypatch.setattr(cli, "setup_logging", lambda: None)
    monkeypatch.setattr(cli, "_POLL_SECONDS", 0)
    monkeypatch.setattr(
        cli, "load_backend_config",
        lambda: {"kind": "http", "http": {"url": BASE, "api_key_env": "AMPERSTAND_API_KEY"}},
    )
    runner = CliRunner()
    return lambda *args: runner.invoke(cli.app, ["capture-file", *map(str, args)])


def job(status: str, **extra) -> dict:
    return {"id": JOB, "status": status, "title": "Weekly demo", "duration": 25.0, **extra}


@needs_ffmpeg
def test_uploads_audio_and_waits_for_the_saved_doc(run, clip, httpx_mock):
    httpx_mock.add_response(method="POST", url=SUBMIT, status_code=202, json=job("queued", queue_position=1))
    httpx_mock.add_response(method="GET", url=STATUS, json=job("running", done_seconds=10.0))
    httpx_mock.add_response(method="GET", url=STATUS, json=job("done", doc_id="01ABC"))

    result = run(clip, "--tag", "demo", "--source", "https://youtu.be/xyz", "--language", "ru")

    assert result.exit_code == 0, result.output
    upload = httpx_mock.get_requests()[0]
    assert upload.headers["Authorization"] == "Bearer devkey"
    params = upload.url.params
    assert dict(params) == {
        "filename": "audio.m4a",
        "original_name": "Weekly_demo (2).mp4",
        "title": "Weekly demo",
        "source": "https://youtu.be/xyz",
        "tags": "demo",
        "type": "video",
        "language": "ru",
    }
    assert upload.content[4:8] == b"ftyp"  # an M4A container, not the raw video
    assert len(upload.content) < clip.stat().st_size
    assert "transcribed 0:00:10 of 0:00:25 (40%)" in result.output
    assert "Saved: 01ABC — Weekly demo" in result.output


@needs_ffmpeg
def test_no_wait_returns_once_queued(run, clip, httpx_mock):
    httpx_mock.add_response(method="POST", url=SUBMIT, status_code=202, json=job("queued", queue_position=1))
    result = run(clip, "--no-wait")
    assert result.exit_code == 0, result.output
    assert f"Queued: transcription job {JOB}" in result.output
    assert len(httpx_mock.get_requests()) == 1


@needs_ffmpeg
def test_a_failed_job_exits_nonzero(run, clip, httpx_mock):
    httpx_mock.add_response(method="POST", url=SUBMIT, status_code=202, json=job("running", done_seconds=0))
    httpx_mock.add_response(method="GET", url=STATUS, json=job("failed", error="RuntimeError: model exploded"))
    result = run(clip)
    assert result.exit_code == 1 and "transcription failed: RuntimeError: model exploded" in result.output


@needs_ffmpeg
def test_server_without_transcription_explains(run, clip, httpx_mock):
    httpx_mock.add_response(
        method="POST", url=SUBMIT, status_code=503,
        json={"detail": {"error": "transcription_unavailable", "detail": "faster-whisper is not installed"}},
    )
    result = run(clip)
    assert result.exit_code == 1 and "faster-whisper is not installed" in result.output


@needs_ffmpeg
def test_ctrl_c_leaves_the_job_running(run, clip, httpx_mock, monkeypatch):
    httpx_mock.add_response(method="POST", url=SUBMIT, status_code=202, json=job("running", done_seconds=0))

    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr("time.sleep", interrupt)
    result = run(clip)
    assert result.exit_code == 130 and "The server keeps going" in result.output


def test_rejects_a_file_without_audio(run, tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    silent = tmp_path / "silent.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2", str(silent)], check=True)
    result = run(silent)
    assert result.exit_code == 1 and "has no audio track" in result.output


def test_rejects_a_bad_language_code(run, tmp_path):
    f = tmp_path / "a.m4a"
    f.write_bytes(b"x")
    result = run(f, "--language", "english")
    assert result.exit_code == 1 and "two-letter code" in result.output
