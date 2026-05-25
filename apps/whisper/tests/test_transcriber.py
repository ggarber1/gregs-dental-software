from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch


def _fresh_transcriber():
    """Reload transcriber with clean module state."""
    if "app.transcriber" in sys.modules:
        del sys.modules["app.transcriber"]
    import app.transcriber as t
    t._model_instance = None
    return t


def test_transcribe_returns_joined_segments():
    t = _fresh_transcriber()
    seg1 = MagicMock()
    seg1.text = " Patient tolerated well. "
    seg2 = MagicMock()
    seg2.text = " No complications."
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([seg1, seg2], MagicMock())

    with patch("app.transcriber._model", return_value=mock_model):
        result = t.transcribe(b"fake-audio-bytes")

    assert result == "Patient tolerated well. No complications."
    # Confirm audio was not written to disk
    mock_model.transcribe.assert_called_once()
    call_args = mock_model.transcribe.call_args
    import io
    assert isinstance(call_args[0][0], io.BytesIO)


def test_transcribe_empty_audio_returns_empty():
    t = _fresh_transcriber()
    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], MagicMock())

    with patch("app.transcriber._model", return_value=mock_model):
        result = t.transcribe(b"")

    assert result == ""
