from uuid import uuid4
from typing import Optional
from time import time
from uuid import UUID
import re
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, Signer
from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator


app = FastAPI(title="KR2 FastAPI")


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Имя пользователя")
    email: EmailStr
    age: Optional[int] = Field(default=None, gt=0)
    is_subscribed: Optional[bool] = None


class Product(BaseModel):
    product_id: int
    name: str
    category: str
    price: float


class CommonHeaders(BaseModel):
    user_agent: str = Field(alias="User-Agent")
    accept_language: str = Field(alias="Accept-Language")

    @field_validator("accept_language")
    @classmethod
    def validate_accept_language(cls, value: str) -> str:
        if not is_valid_accept_language(value):
            raise ValueError("Invalid Accept-Language format")
        return value


sample_products = [
    Product(product_id=123, name="Smartphone", category="Electronics", price=599.0),
    Product(product_id=456, name="Phone Case", category="Accessories", price=19.0),
    Product(product_id=789, name="Iphone", category="Electronics", price=1299.0),
    Product(product_id=101, name="Headphones", category="Accessories", price=99.0),
    Product(product_id=202, name="Smartwatch", category="Electronics", price=299.0),
]


valid_credentials = {
    "user123": "password123",
}
active_sessions: dict[str, str] = {}

SECRET_KEY = "kr2-super-secret-key"
signer = Signer(SECRET_KEY)

SESSION_MAX_AGE_SECONDS = 300
SESSION_REFRESH_AFTER_SECONDS = 180


async def get_login_data(request: Request) -> tuple[str, str]:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        payload = await request.json()
    else:
        form_data = await request.form()
        payload = dict(form_data)

    username = payload.get("username")
    password = payload.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    return str(username), str(password)


def build_session_token(user_id: str, timestamp: int) -> str:
    payload = f"{user_id}.{timestamp}"
    signature = signer.get_signature(payload.encode()).decode()
    return f"{payload}.{signature}"


def parse_session_token(session_token: str) -> tuple[str, int]:
    try:
        user_id, timestamp_raw, signature = session_token.rsplit(".", 2)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    signed_value = f"{user_id}.{timestamp_raw}.{signature}".encode()

    try:
        signer.unsign(signed_value)
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    try:
        UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    if not timestamp_raw.isdigit():
        raise HTTPException(status_code=401, detail="Invalid session")

    timestamp = int(timestamp_raw)
    current_timestamp = int(time())

    if timestamp > current_timestamp:
        raise HTTPException(status_code=401, detail="Invalid session")

    return user_id, timestamp


def is_valid_accept_language(value: str) -> bool:
    pattern = r"^[a-z]{2}(?:-[A-Z]{2})?(?:,\s*[a-z]{2}(?:-[A-Z]{2})?(?:;q=(?:0(?:\.\d+)?|1(?:\.0+)?))?)*$"
    return bool(re.fullmatch(pattern, value))


def get_common_headers(
    user_agent: Optional[str] = Header(default=None, alias="User-Agent"),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
) -> CommonHeaders:
    if not user_agent or not accept_language:
        raise HTTPException(status_code=400, detail="Required headers are missing")

    try:
        return CommonHeaders.model_validate(
            {
                "User-Agent": user_agent,
                "Accept-Language": accept_language,
            }
        )
    except ValidationError as exc:
        first_error = exc.errors()[0]
        message = str(first_error.get("msg", "Invalid headers"))
        if "Invalid Accept-Language format" in message:
            message = "Invalid Accept-Language format"
        raise HTTPException(status_code=400, detail=message) from exc


@app.post("/create_user", response_model=UserCreate)
def create_user(user: UserCreate) -> UserCreate:
    return user


@app.get("/products/search", response_model=list[Product])
def search_products(
    keyword: str = Query(..., min_length=1),
    category: Optional[str] = None,
    limit: int = Query(default=10, gt=0),
) -> list[Product]:
    keyword_lower = keyword.lower()

    matched_products = [
        product for product in sample_products if keyword_lower in product.name.lower()
    ]

    if category:
        category_lower = category.lower()
        matched_products = [
            product
            for product in matched_products
            if product.category.lower() == category_lower
        ]

    return matched_products[:limit]


@app.get("/product/{product_id}", response_model=Product)
def get_product(product_id: int) -> Product:
    for product in sample_products:
        if product.product_id == product_id:
            return product

    raise HTTPException(status_code=404, detail="Product not found")


@app.post("/login")
async def login(request: Request) -> JSONResponse:
    username, password = await get_login_data(request)

    if valid_credentials.get(username) != password:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    user_id = str(uuid4())
    active_sessions[user_id] = username
    now_timestamp = int(time())
    session_token = build_session_token(user_id, now_timestamp)

    response = JSONResponse(content={"message": "Login successful"})
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,
        max_age=SESSION_MAX_AGE_SECONDS,
    )
    return response


@app.get("/profile")
def profile(request: Request) -> JSONResponse:
    session_token = request.cookies.get("session_token")

    if not session_token:
        return JSONResponse(status_code=401, content={"message": "Invalid session"})

    try:
        user_id, last_activity_timestamp = parse_session_token(session_token)
    except HTTPException:
        return JSONResponse(status_code=401, content={"message": "Invalid session"})

    username = active_sessions.get(user_id)
    if not username:
        return JSONResponse(status_code=401, content={"message": "Invalid session"})

    current_timestamp = int(time())
    session_age = current_timestamp - last_activity_timestamp

    if session_age > SESSION_MAX_AGE_SECONDS:
        return JSONResponse(status_code=401, content={"message": "Session expired"})

    response = JSONResponse(content={"user_id": user_id, "username": username})

    should_refresh = (
        SESSION_REFRESH_AFTER_SECONDS <= session_age < SESSION_MAX_AGE_SECONDS
    )

    if should_refresh:
        refreshed_token = build_session_token(user_id, current_timestamp)
        response.set_cookie(
            key="session_token",
            value=refreshed_token,
            httponly=True,
            secure=False,
            max_age=SESSION_MAX_AGE_SECONDS,
        )

    return response


@app.get("/user")
def user_profile(request: Request) -> JSONResponse:
    return profile(request)


@app.get("/headers")
def get_headers(common_headers: CommonHeaders = Depends(get_common_headers)) -> JSONResponse:
    return JSONResponse(
        content={
            "User-Agent": common_headers.user_agent,
            "Accept-Language": common_headers.accept_language,
        }
    )


@app.get("/info")
def get_info(common_headers: CommonHeaders = Depends(get_common_headers)) -> JSONResponse:
    response = JSONResponse(
        content={
            "message": "Добро пожаловать! Ваши заголовки успешно обработаны.",
            "headers": {
                "User-Agent": common_headers.user_agent,
                "Accept-Language": common_headers.accept_language,
            },
        }
    )
    response.headers["X-Server-Time"] = datetime.now().isoformat()
    return response
