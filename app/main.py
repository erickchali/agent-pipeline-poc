"""A deliberately small notes API. It exists so the agents have real code to work on."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_session
from app.models import Note
from app.schemas import NoteCreate, NoteRead

SessionDep = Annotated[Session, Depends(get_session)]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Notes API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate, session: SessionDep) -> Note:
    note = Note(title=payload.title, body=payload.body)
    session.add(note)
    session.commit()
    return note


@app.get("/notes", response_model=list[NoteRead])
def list_notes(session: SessionDep) -> list[Note]:
    return list(session.scalars(select(Note).order_by(Note.id)))


@app.get("/notes/{note_id}", response_model=NoteRead)
def get_note(note_id: int, session: SessionDep) -> Note:
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note
