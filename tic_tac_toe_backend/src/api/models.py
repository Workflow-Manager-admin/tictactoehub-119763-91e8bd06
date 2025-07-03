"""Database models and related Pydantic schemas for Tic Tac Toe backend."""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
import datetime
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List

Base = declarative_base()

# SQLAlchemy database models

class User(Base):
    """User database model."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    # Remove ambiguous games/owner relationship to avoid SQLAlchemy mapping errors.
    # You may add explicit relationships for games_as_x/games_as_o if needed, but not a broad 'games' link.

class Game(Base):
    """Game database model."""
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String(24), default="waiting")  # waiting, ongoing, finished
    player_x_id = Column(Integer, ForeignKey("users.id"))
    player_o_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    current_turn = Column(String(1), default="X")
    winner = Column(String(1), nullable=True)   # "X", "O", "D" (Draw), or None
    board_state = Column(String(9), default=" " * 9)  # 9-character string, e.g. "X OX O   "
    # Removed ambiguous owner/games relationship.
    # Optionally, you can add:
    # player_x = relationship("User", foreign_keys=[player_x_id])
    # player_o = relationship("User", foreign_keys=[player_o_id])

    moves = relationship("Move", back_populates="game", cascade="all, delete")

class Move(Base):
    """Move database model."""
    __tablename__ = "moves"
    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id"))
    player = Column(String(1))   # "X" or "O"
    position = Column(Integer)   # 0-8
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    game = relationship("Game", back_populates="moves")

# --- Pydantic Schemas (for requests, responses) ---

# PUBLIC_INTERFACE
class UserCreate(BaseModel):
    """Schema for user registration."""
    username: str = Field(..., description="Unique username")
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="Password")

# PUBLIC_INTERFACE
class UserLogin(BaseModel):
    """Schema for user login."""
    username: str
    password: str

# PUBLIC_INTERFACE
class UserInDB(BaseModel):
    """Schema for user details (database/internal)."""
    id: int
    username: str
    email: EmailStr

    class Config:
        orm_mode = True

# PUBLIC_INTERFACE
class GameCreate(BaseModel):
    """Schema to create new game."""
    pass  # No additional info needed for creation.

# PUBLIC_INTERFACE
class MoveCreate(BaseModel):
    """Schema for submitting a move."""
    position: int = Field(..., ge=0, le=8, description="Board position [0-8]")

# PUBLIC_INTERFACE
class MoveResponse(BaseModel):
    id: int
    player: str
    position: int

    class Config:
        orm_mode = True

# PUBLIC_INTERFACE
class GameStateResponse(BaseModel):
    id: int
    board_state: str = Field(..., min_length=9, max_length=9)
    current_turn: str
    status: str
    winner: Optional[str]
    moves: List[MoveResponse] = []

    class Config:
        orm_mode = True
