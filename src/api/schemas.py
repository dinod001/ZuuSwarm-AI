from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Chat Session CRUD Schemas
# ---------------------------------------------------------

class ChatSessionCreateRequest(BaseModel):
    """Schema for creating a new chat session."""
    employer_id: str = Field(..., description="ID of the employer")
    title: Optional[str] = Field("New Chat", description="Title of the chat session")
    session_id: Optional[str] = Field(None, description="Optional custom session ID")

class ChatSessionUpdateRequest(BaseModel):
    """Schema for updating an existing chat session."""
    title: Optional[str] = Field(None, description="New title for the chat session")
    archived: Optional[int] = Field(None, description="Archive status (1 for archived, 0 for active)")

class ChatSessionMeta(BaseModel):
    """Metadata for a single chat session."""
    session_id: str
    employer_id: str
    title: str
    last_message_at: Optional[int] = None
    created_at: int
    updated_at: int
    archived: int
    
    class Config:
        from_attributes = True

class ChatSessionListResponse(BaseModel):
    """Schema for a paginated list of chat sessions."""
    sessions: List[ChatSessionMeta]
    total: Optional[int] = None


# ---------------------------------------------------------
# Chat Router Schemas
# ---------------------------------------------------------

class ChatRequest(BaseModel):
    """Inbound chat message from the UI."""
    user_id: str = Field(..., description="Employee ID (e.g. 'EMP-0042')")
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., description="The user's message / issue report")
    user_email: Optional[str] = Field(None, description="Employee email (for clearance checks)")

class ChatResponse(BaseModel):
    """Full response returned to the UI after the pipeline completes."""
    answer: str
    route: str = "direct"
    cached: bool = False
    latency_ms: int = 0
    timings: Optional[Dict[str, int]] = None
    ticket_id: Optional[str] = None
    model_used: Optional[str] = None

class TurnItem(BaseModel):
    role: str
    content: str
    ts: Optional[float] = None

class SessionTurnsResponse(BaseModel):
    session_id: str
    user_id: str
    turn_count: int = 0
    turns: List[TurnItem]

class ChatResetRequest(BaseModel):
    user_id: str
    session_id: str

class ChatResetResponse(BaseModel):
    status: str = "ok"
    cleared: bool = False
    user_id: str = ""
    session_id: str = ""

class SessionWarmupRequest(BaseModel):
    session_id: str
    user_id: str

class SessionWarmupResponse(BaseModel):
    status: str = "ok"
    warmed: bool = True
    st_turn_count: int = 0
    latency_ms: int = 0
