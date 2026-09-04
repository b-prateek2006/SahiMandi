from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext

from app.auth_service import SessionIdentity, issue_otp, issue_token, verify_otp
from app.models import CentreUser, Farmer, Notification, SessionLocal
from app.schemas import OfficerLoginInput, OtpRequest, OtpVerify


router = APIRouter(prefix="/auth", tags=["auth"])
passwords = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


@router.post("/otp/request")
def request_otp(data: OtpRequest):
    code = issue_otp(data.phone)
    with SessionLocal.begin() as session:
        session.add(Notification(phone=data.phone, body=f"Mock OTP: {code}", channel="SMS", status="SENT"))
    print(f"Mock OTP for {data.phone}: {code}")
    return {"message": "OTP printed to the mock notification mechanism."}


@router.post("/otp/verify")
def otp_verify(data: OtpVerify):
    if not verify_otp(data.phone, data.code):
        raise HTTPException(status_code=401, detail="Invalid or expired OTP.")
    with SessionLocal() as session:
        farmer = session.query(Farmer).filter(Farmer.phone == data.phone).first()
        if farmer is None:
            raise HTTPException(status_code=404, detail="Register before signing in.")
        token = issue_token(SessionIdentity(role="FARMER", subject_id=farmer.id))
    return {"token": token}


@router.post("/officer/login")
def officer_login(data: OfficerLoginInput):
    with SessionLocal() as session:
        user = session.query(CentreUser).filter(CentreUser.username == data.username).first()
        if user is None or not user.password_hash or not passwords.verify(data.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        token = issue_token(SessionIdentity(role=user.role or "OFFICER", subject_id=user.id, centre_id=user.centre_id))
    return {"token": token, "role": user.role, "centre_id": user.centre_id}
