from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, EmailStr, Field


app = FastAPI(title="KR2 FastAPI")


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Имя пользователя")
    email: EmailStr
    age: Optional[int] = Field(default=None, gt=0)
    is_subscribed: Optional[bool] = None


@app.post("/create_user", response_model=UserCreate)
def create_user(user: UserCreate) -> UserCreate:
    return user
