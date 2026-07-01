"""Shared pytest fixtures and configuration."""
import os

import pytest

# Set dummy env vars so the app initialises without real keys
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("API_KEY", "sk-test-dummy-key-for-ci")
os.environ.setdefault("ENV", "test")
