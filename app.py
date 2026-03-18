from uuid import uuid4
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, Signer
from pydantic import BaseModel, EmailStr, Field


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


def build_session_token(user_id: str) -> str:
    return signer.sign(user_id.encode()).decode()


def parse_session_token(session_token: str) -> str:
    try:
        user_id = signer.unsign(session_token.encode()).decode()
    except BadSignature as exc:
        raise HTTPException(status_code=401, detail="Unauthorized") from exc

    return user_id


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
    session_token = build_session_token(user_id)

    response = JSONResponse(content={"message": "Login successful"})
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        max_age=3600,
    )
    return response


@app.get("/profile")
def profile(request: Request) -> JSONResponse:
    session_token = request.cookies.get("session_token")

    if not session_token:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    try:
        user_id = parse_session_token(session_token)
    except HTTPException:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    username = active_sessions.get(user_id)
    if not username:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})

    return JSONResponse(content={"user_id": user_id, "username": username})


@app.get("/user")
def user_profile(request: Request) -> JSONResponse:
    return profile(request)
