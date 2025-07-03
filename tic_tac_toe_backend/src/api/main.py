from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .models import (
    UserCreate, UserInDB,
    GameCreate, MoveCreate, GameStateResponse, MoveResponse,
    Base, User, Game, Move,
)
from .deps import (
    get_db,
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

import os

app = FastAPI(
    title="Tic Tac Toe Backend API",
    description="Backend for Tic Tac Toe game with user management and game logic",
    version="0.1.0",
    openapi_tags=[
        {"name": "users", "description": "User registration and authentication"},
        {"name": "games", "description": "Game management and moves"}
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    """Creates database tables at startup if they do not exist."""
    Base.metadata.create_all(bind=__import__('sqlalchemy').create_engine(
        os.getenv("DATABASE_URL", "sqlite:///./tictactoe.db"),
        connect_args={"check_same_thread": False} if "sqlite" in os.getenv("DATABASE_URL", "") else {}
    ))

@app.get("/")
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}

# --- User Registration and Auth ---

router = APIRouter(prefix="/api/users", tags=["users"])

# PUBLIC_INTERFACE
@router.post("/register", response_model=UserInDB, summary="Register a new user")
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user."""
    # Check for duplicate username/email
    if db.query(User).filter((User.username == user.username) | (User.email == user.email)).first():
        raise HTTPException(status_code=400, detail="Username/email already registered.")
    hashed_pw = hash_password(user.password)
    db_user = User(username=user.username, email=user.email, password_hash=hashed_pw)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return UserInDB.from_orm(db_user)

# PUBLIC_INTERFACE
@router.post("/login", summary="Login and receive an access token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Authenticate user and return token."""
    db_user = db.query(User).filter(User.username == form_data.username).first()
    if not db_user or not verify_password(form_data.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = create_access_token(data={"sub": db_user.username})
    return {"access_token": access_token, "token_type": "bearer", "user_id": db_user.id}

app.include_router(router)

# --- Game Endpoints ---

game_router = APIRouter(prefix="/api/games", tags=["games"])

# PUBLIC_INTERFACE
@game_router.post("", response_model=GameStateResponse, summary="Create a new game")
def create_game(
    _: GameCreate = Depends(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new game as X with authenticated user."""
    new_game = Game(
        player_x_id=current_user.id,
        current_turn="X",
        status="waiting",
        board_state=" " * 9,
    )
    db.add(new_game)
    db.commit()
    db.refresh(new_game)
    return GameStateResponse(
        id=new_game.id,
        board_state=new_game.board_state,
        current_turn=new_game.current_turn,
        status=new_game.status,
        winner=new_game.winner,
        moves=[],
    )

# PUBLIC_INTERFACE
@game_router.get("/{game_id}", response_model=GameStateResponse, summary="Get game state")
def get_game_state(
    game_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch full game state for a given game."""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    # Authorization: User must be participant
    if current_user.id not in [game.player_x_id, game.player_o_id]:
        raise HTTPException(status_code=403, detail="Not a participant in this game")
    moves = [
        MoveResponse(
            id=m.id, player=m.player,
            position=m.position
        ) for m in game.moves
    ]
    return GameStateResponse(
        id=game.id,
        board_state=game.board_state,
        current_turn=game.current_turn,
        status=game.status,
        winner=game.winner,
        moves=moves,
    )

# PUBLIC_INTERFACE
@game_router.post("/{game_id}/move", response_model=GameStateResponse, summary="Play a move")
def play_move(
    game_id: int,
    move: MoveCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Play a move in the given game, with move validation and result update."""
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # If O slot open, allow join as O
    if game.status == "waiting" and game.player_o_id is None and current_user.id != game.player_x_id:
        game.player_o_id = current_user.id
        game.status = "ongoing"

    # Ensure player is X or O
    if current_user.id not in [game.player_x_id, game.player_o_id]:
        raise HTTPException(status_code=403, detail="You're not a player in this game.")

    # Check game not finished
    if game.status == "finished":
        raise HTTPException(status_code=400, detail="Game has finished.")

    board = list(game.board_state)
    position = move.position
    if not (0 <= position < 9) or board[position] != " ":
        raise HTTPException(status_code=400, detail="Invalid move: Position taken or out of range.")

    # Determine expected player
    player_char = "X" if current_user.id == game.player_x_id else "O"
    if game.current_turn != player_char:
        raise HTTPException(status_code=400, detail="It's not your turn.")

    board[position] = player_char
    game.board_state = "".join(board)

    # Record the move
    mv = Move(game_id=game.id, player=player_char, position=position)
    db.add(mv)

    # Check game outcome
    def _check_winner(board, char):
        wins = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6],
        ]
        for combo in wins:
            if all(board[i] == char for i in combo):
                return True
        return False

    if _check_winner(board, player_char):
        game.status = "finished"
        game.winner = player_char
    elif all(s != " " for s in board):
        game.status = "finished"
        game.winner = "D"  # Draw
    else:
        game.current_turn = "O" if game.current_turn == "X" else "X"

    db.commit()
    db.refresh(game)
    moves = [
        MoveResponse(
            id=m.id, player=m.player,
            position=m.position
        ) for m in game.moves
    ]
    return GameStateResponse(
        id=game.id,
        board_state=game.board_state,
        current_turn=game.current_turn,
        status=game.status,
        winner=game.winner,
        moves=moves,
    )

app.include_router(game_router)

