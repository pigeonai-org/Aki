"""
Pytest Configuration

Shared fixtures and configuration for tests.
"""

import pytest


@pytest.fixture
def sample_task():
    """Sample task for testing."""
    return "Transcribe and translate video.mp4 from English to Chinese"


@pytest.fixture
def sample_subtitle_entries():
    """Sample subtitle entries for testing."""
    return [
        {
            "index": 1,
            "start_time": "00:00:00,000",
            "end_time": "00:00:02,000",
            "text": "Hello world",
        },
        {
            "index": 2,
            "start_time": "00:00:02,500",
            "end_time": "00:00:05,000",
            "text": "This is a test",
        },
    ]


@pytest.fixture
def mock_api_key():
    """Mock API key for testing."""
    return "sk-test-key-for-testing"
