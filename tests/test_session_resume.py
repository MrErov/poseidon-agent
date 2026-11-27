"""Tests for API session resume functionality."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from poseidon.core import PhaseRunner
from poseidon.prompt_builder import PromptBuilder


def test_prompt_builder_resumed_messages() -> None:
    """Test that resumed messages are prepended to new messages."""
    builder = PromptBuilder()
    cold_memory = "You are a helpful assistant."
    specification = "Test spec"

    # Create some resumed messages (simulating prior conversation)
    resumed = [
        {"role": "system", "content": "Old system prompt"},
        {"role": "user", "content": "Previous user message"},
        {"role": "assistant", "content": "Previous assistant response"},
    ]

    messages = builder.build_messages(
        phase="1a",
        spec_path=Path("spec.md"),
        cold_memory=cold_memory,
        specification=specification,
        resumed_messages=resumed,
    )

    # Should have: resumed messages (minus system) + new system + new user
    # = 2 (resumed user+assistant) + 1 (new system) + 1 (new user) = 4
    assert len(messages) == 4

    # First message should be the first resumed user message (system from resumed filtered out)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Previous user message"

    # Last message should be the new user message with intro + spec
    assert messages[-1]["role"] == "user"
    assert "Test spec" in messages[-1]["content"]


def test_prompt_builder_no_resumed_messages() -> None:
    """Test normal behavior without resumed messages."""
    builder = PromptBuilder()
    cold_memory = "You are a helpful assistant."
    specification = "Test spec"

    messages = builder.build_messages(
        phase="1a",
        spec_path=Path("spec.md"),
        cold_memory=cold_memory,
        specification=specification,
        resumed_messages=None,
    )

    # Should have just system + user = 2
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_prompt_builder_resumed_filters_system() -> None:
    """Test that system messages from resumed history are filtered out."""
    builder = PromptBuilder()
    cold_memory = "New system prompt"

    resumed = [
        {"role": "system", "content": "Old system"},
        {"role": "user", "content": "User 1"},
        {"role": "assistant", "content": "Assistant 1"},
        {"role": "system", "content": "Another system"},  # Should also be filtered
        {"role": "user", "content": "User 2"},
    ]

    messages = builder.build_messages(
        phase="1a",
        spec_path=Path("spec.md"),
        cold_memory=cold_memory,
        specification="Test",
        resumed_messages=resumed,
    )

    # Should have: 3 non-system resumed + 1 new system + 1 new user = 5
    assert len(messages) == 5

    # No system messages except the new one (which should be at index 3 after resumed messages)
    system_count = sum(1 for m in messages if m["role"] == "system")
    assert system_count == 1

    # First 3 messages should be from resumed history (non-system)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "User 1"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Assistant 1"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "User 2"

    # New system message should be at index 3
    assert messages[3]["role"] == "system"
    assert messages[3]["content"] == "New system prompt"


def test_phase_runner_session_file_path(tmp_path: Path) -> None:
    """Test session file path generation."""
    with patch("poseidon.core.get_working_dir", return_value=tmp_path):
        runner = PhaseRunner()
        path = runner._session_file_path("1a", "session123")
        assert path.name == "session_1a_session123.json"
        assert path.parent == tmp_path / ".poseidon" / "sessions"


def test_phase_runner_save_and_load_session(tmp_path: Path) -> None:
    """Test saving and loading session state."""
    with patch("poseidon.core.get_working_dir", return_value=tmp_path):
        runner = PhaseRunner()

        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        session_file = runner._save_session(
            phase="1a",
            messages=messages,
            spec_path="spec.md",
            context_path=None,
            model_name="test-model",
            executor="api",
        )

        assert session_file.is_file()
        assert session_file.name.startswith("session_1a_")

        loaded = runner._load_session(session_file)
        assert loaded is not None
        assert loaded["phase"] == "1a"
        assert loaded["messages"] == messages
        assert loaded["spec_path"] == "spec.md"
        assert loaded["model_name"] == "test-model"
        assert loaded["executor"] == "api"


def test_phase_runner_load_nonexistent_session(tmp_path: Path) -> None:
    """Test loading non-existent session returns None."""
    with patch("poseidon.core.get_working_dir", return_value=tmp_path):
        runner = PhaseRunner()
        fake_path = tmp_path / ".poseidon" / "sessions" / "nonexistent.json"
        loaded = runner._load_session(fake_path)
        assert loaded is None


def test_phase_runner_session_auto_find_latest(tmp_path: Path) -> None:
    """Test auto-finding latest session for a phase."""
    with patch("poseidon.core.get_working_dir", return_value=tmp_path):
        runner = PhaseRunner()

        # Create multiple sessions for phase 1a
        messages = [{"role": "user", "content": "test"}]

        # Create older session
        import time
        old_session = tmp_path / ".poseidon" / "sessions" / "session_1a_old.json"
        old_session.parent.mkdir(parents=True, exist_ok=True)
        old_session.write_text(json.dumps({
            "phase": "1a", "messages": messages, "timestamp": time.time() - 100
        }))

        # Create newer session
        new_session = tmp_path / ".poseidon" / "sessions" / "session_1a_new.json"
        new_session.write_text(json.dumps({
            "phase": "1a", "messages": messages, "timestamp": time.time()
        }))

        # Should find the newest
        found = runner._session_file_path("1a")
        assert found.name == "session_1a_new.json"


def test_phase_runner_save_session_on_api_execution(tmp_path: Path) -> None:
    """Test that session is saved after API execution."""
    # Create spec file in actual cwd (where Path("spec.md") will look)
    cwd = Path.cwd()
    spec_file = cwd / "spec.md"
    spec_file.write_text("# Test Spec")

    # Create meta-skills in tmp_path (where get_working_dir returns when patched)
    meta_skills = tmp_path / ".meta-skills"
    meta_skills.mkdir()
    (meta_skills / "01-sdd-spec-writer.md").write_text("Spec Writer instructions")

    try:
        with patch("poseidon.core.get_working_dir", return_value=tmp_path):
            runner = PhaseRunner()

            # Mock execution engine to return content
            mock_engine = MagicMock()
            mock_engine.execute.return_value = "Response content"
            runner.execution_engine = mock_engine

            # Run with API executor (spec.md will be found in actual cwd)
            runner.run(
                phase="1a",
                spec_path="spec.md",
                model_name="test-model",
                executor="api",
            )

            # Check session was saved in tmp_path
            sessions = list((tmp_path / ".poseidon" / "sessions").glob("session_1a_*.json"))
            assert len(sessions) == 1

            loaded = json.loads(sessions[0].read_text())
            assert loaded["phase"] == "1a"
            assert loaded["model_name"] == "test-model"
            assert loaded["executor"] == "api"
            assert len(loaded["messages"]) == 2  # system + user
    finally:
        # Cleanup
        spec_file = Path.cwd() / "spec.md"
        if spec_file.exists():
            spec_file.unlink()


def test_phase_runner_resume_session(tmp_path: Path) -> None:
    """Test resuming from a saved session."""
    # Create spec file in actual cwd
    cwd = Path.cwd()
    spec_file = cwd / "spec.md"
    spec_file.write_text("# Test Spec")

    # Create meta-skills in tmp_path (where get_working_dir returns when patched)
    meta_skills = tmp_path / ".meta-skills"
    meta_skills.mkdir()
    (meta_skills / "01-sdd-spec-writer.md").write_text("Spec Writer instructions")

    try:
        with patch("poseidon.core.get_working_dir", return_value=tmp_path):
            runner = PhaseRunner()

            # Create a session file with prior messages
            resumed_messages = [
                {"role": "system", "content": "Old system"},
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
            ]
            session_data = {
                "phase": "1a",
                "messages": resumed_messages,
                "spec_path": "spec.md",
                "context_path": None,
                "model_name": "test-model",
                "executor": "api",
                "timestamp": time.time(),
            }
            session_file = tmp_path / ".poseidon" / "sessions" / "session_1a_resume.json"
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text(json.dumps(session_data))

            # Mock execution engine
            mock_engine = MagicMock()
            mock_engine.execute.return_value = "Continued response"
            runner.execution_engine = mock_engine

            # Run with resume_session
            runner.run(
                phase="1a",
                spec_path="spec.md",
                model_name="test-model",
                executor="api",
                resume_session="session_1a_resume.json",
            )

            # Verify the execution engine was called with resumed messages
            call_args = mock_engine.execute.call_args
            messages_passed = call_args[0][0]  # First positional arg

            # Should have resumed messages (filtered) + new messages
            # Resumed: user + assistant (system filtered) = 2
            # New: system + user = 2
            # Total = 4
            assert len(messages_passed) == 4

            # First messages should be from resumed history
            assert messages_passed[0]["role"] == "user"
            assert messages_passed[0]["content"] == "First question"
            assert messages_passed[1]["role"] == "assistant"
            assert messages_passed[1]["content"] == "First answer"
    finally:
        # Cleanup
        spec_file = Path.cwd() / "spec.md"
        if spec_file.exists():
            spec_file.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])