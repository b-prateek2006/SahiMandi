from contextlib import asynccontextmanager
from threading import Event, Thread
from time import sleep

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.bookings import router as bookings_router
from app.routers.district import router as district_router
from app.routers.farmers import router as farmers_router
from app.routers.officer import router as officer_router
from app.routers.sim import router as sim_router
from app.models import SessionLocal
from app.notify import configured_gateway, process_queued_notifications


def notification_worker(stop: Event) -> None:
    gateway = configured_gateway()
    while not stop.is_set():
        process_queued_notifications(SessionLocal, gateway)
        stop.wait(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = Event()
    worker = Thread(target=notification_worker, args=(stop,), daemon=True)
    worker.start()
    yield
    stop.set()
    worker.join(timeout=5)


app = FastAPI(title="SahiMandi", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(farmers_router)
app.include_router(bookings_router)
app.include_router(officer_router)
app.include_router(sim_router)
app.include_router(district_router)
