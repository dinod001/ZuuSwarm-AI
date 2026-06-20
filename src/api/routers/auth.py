from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from infrastructure.db.sql_client import get_sql_engine
from sqlalchemy import text
from loguru import logger

router = APIRouter()

class LoginRequest(BaseModel):
    email: EmailStr

class LoginResponse(BaseModel):
    user_id: str
    name: str
    email: str
    role: str

@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Fetch employee details by email to resolve the actual user_id (EMP-XXXX)."""
    engine = get_sql_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT id, name, email, role FROM employees WHERE email = :email AND is_active = TRUE"),
                {"email": req.email}
            ).fetchone()
            
            if not result:
                raise HTTPException(status_code=401, detail="Employee not found or inactive.")
                
            return LoginResponse(
                user_id=result[0],
                name=result[1],
                email=result[2],
                role=result[3]
            )
    except Exception as e:
        logger.error(f"Login failed for {req.email}: {e}")
        raise HTTPException(status_code=500, detail="Database connection error.")
