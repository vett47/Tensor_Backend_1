from re import fullmatch

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

app = FastAPI()


class Base(DeclarativeBase):
    pass


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    specialization: Mapped[str] = mapped_column(String, nullable=False)

    @property
    def master_id(self) -> int:
        return self.id


class Service:
    def __init__(self, service_id: int, name: str):
        self.service_id = service_id
        self.name = name


class Appoinment:
    def __init__(self, appointment_id: int, client_name: str, master_id: int, service_id: int, time: str):
        self.appointment_id = appointment_id
        self.client_name = client_name
        self.master_id = master_id
        self.service_id = service_id
        self.time = time


engine = create_engine("sqlite:///masters.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)


def seed_masters() -> None:
    with SessionLocal() as session:
        if session.query(Master).count() == 0:
            session.add_all([
                Master(id=1, name="Анна", specialization="Парикмахер"),
                Master(id=2, name="Мария", specialization="Визажист"),
            ])
            session.commit()


seed_masters()

services = [Service(1, "Стрижка")]
appointments: list[Appoinment] = []
categories = [
    {"id": 1, "name": "Стрижки и укладки", "servicesCount": 5},
    {"id": 2, "name": "Маникюр и педикюр", "servicesCount": 5},
    {"id": 3, "name": "Брови и ресницы", "servicesCount": 4},
    {"id": 4, "name": "Спа-процедуры", "servicesCount": 4},
]


def master_to_dict(master: Master) -> dict:
    return {"id": master.id, "name": master.name, "specialization": master.specialization}


def get_master(master_id: int) -> Master | None:
    with SessionLocal() as session:
        master = session.get(Master, master_id)
        if master is not None:
            session.expunge(master)
        return master


def get_service(service_id: int) -> Service | None:
    return next((service for service in services if service.service_id == service_id), None)


def is_working_time(value: str) -> bool:
    if not fullmatch(r"\d{2}:\d{2}", value):
        return False
    hours, minutes = map(int, value.split(":"))
    if not 0 <= hours <= 23 or not 0 <= minutes <= 59:
        return False
    time_in_minutes = hours * 60 + minutes
    return 8 * 60 <= time_in_minutes <= 20 * 60


def create_appointment(client_name: str, master_id: int, service_id: int, time: str) -> Appoinment | None:
    if not all((client_name.strip(), master_id, service_id, time)):
        return None
    master = get_master(master_id)
    service = get_service(service_id)
    if master is None or service is None or not is_working_time(time):
        return None
    appointment = Appoinment(len(appointments) + 1, client_name, master.master_id, service.service_id, time)
    appointments.append(appointment)
    return appointment


@app.get("/masters")
def get_masters(specialization: str | None = None) -> list[dict]:
    with SessionLocal() as session:
        query = session.query(Master)
        if specialization is not None:
            query = query.filter(Master.specialization == specialization)
        return [master_to_dict(master) for master in query.order_by(Master.id).all()]


@app.get("/masters/{master_id}")
def get_master_endpoint(master_id: int) -> dict:
    master = get_master(master_id)
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    return master_to_dict(master)


@app.get("/categories")
def get_categories() -> list[dict]:
    return categories


@app.get("/categories/{category_id}")
def get_category(category_id: int) -> dict:
    category = next((item for item in categories if item["id"] == category_id), None)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


if __name__ == "__main__":
    from fastapi.testclient import TestClient

    client = TestClient(app)
    seed_masters()
    checks = (
        "/masters",
        "/masters?specialization=Парикмахер",
        "/masters/1",
        "/masters/999",
        "/categories",
        "/categories/1",
        "/categories/999",
    )
    for url in checks:
        response = client.get(url)
        print(url, response.status_code, response.json())

    appointments.clear()
    create_appointment("Иванова А.А.", 1, 1, "10:00")
    create_appointment("Петрова А.А.", 2, 1, "11:00")
    print("Список записей:")
    for appointment in appointments:
        print(appointment.client_name, appointment.time)

    appointments.clear()
    create_appointment("", 1, 1, "12:00")
    print("Пустое имя — записей:", len(appointments))

    appointments.clear()
    create_appointment("Сидорова А.А.", 1, 1, "00:00")
    print("Время 00:00 — записей:", len(appointments))
