"""Tests for the OpenAI Tools handler and Messaging Services."""

import pytest
from unittest.mock import patch, MagicMock

from ai import tools
from services import messaging
from state.conversation_state import ConversationState


@pytest.fixture
def mock_state():
    state = ConversationState(call_sid="TEST_SID123", caller_number="+15550001111")
    return state


def test_schema_valid():
    """Ensure the predefined tools schema is valid for OpenAI."""
    assert len(tools.OPENAI_TOOLS) >= 2
    
    send_doc_tool = next(t for t in tools.OPENAI_TOOLS if t["function"]["name"] == "send_document")
    assert send_doc_tool["type"] == "function"
    assert "document_type" in send_doc_tool["function"]["parameters"]["properties"]
    
    # Assert dynamic properties are populating correctly from Master Manager
    assert "fan" in send_doc_tool["function"]["parameters"]["properties"]["document_type"]["enum"]


def test_resolve_document():
    """Test that Master Manager resolves documents correctly."""
    doc = messaging.resolve_document("fan")
    assert doc is not None
    assert doc.name == "Fan Brochure 2026"
    assert doc.url.startswith("http")
    
    invalid = messaging.resolve_document("spaceships")
    assert invalid is None


@patch("services.messaging._send_whatsapp_mock")
def test_execute_tool_whatsapp(mock_send, mock_state):
    """Test that executing the send_document tool routes to WhatsApp mock service."""
    mock_send.return_value = {"success": True, "message": "Success"}
    
    args = {"document_type": "fan", "method": "whatsapp"}
    result = tools.execute_tool("send_document", args, mock_state)
    
    assert "Success" in result
    mock_send.assert_called_once()
    assert mock_state.actions_taken[0]["action"] == "send_document:fan:whatsapp"


@patch("services.messaging._send_email_mock")
def test_execute_tool_email(mock_send, mock_state):
    """Test that executing email tool correctly validates."""
    mock_send.return_value = {"success": True, "message": "Success"}
    
    # Missing email address should return error string to GPT, NOT throw exception
    args_missing = {"document_type": "wire", "method": "email"}
    result1 = tools.execute_tool("send_document", args_missing, mock_state)
    assert "Error: Email address is required" in result1
    
    # Proper email address should work
    args_valid = {"document_type": "wire", "method": "email", "email_address": "test@test.com"}
    result2 = tools.execute_tool("send_document", args_valid, mock_state)
    assert "Success" in result2
    mock_send.assert_called_once()


def test_execute_tool_end_call(mock_state):
    """Test the end_call_gracefully tool."""
    args = {"reason": "Customer busy"}
    result = tools.execute_tool("end_call_gracefully", args, mock_state)
    
    assert "Customer busy" in result
    assert mock_state.actions_taken[0]["action"] == "end_call"
    assert mock_state.actions_taken[0]["reason"] == "Customer busy"
