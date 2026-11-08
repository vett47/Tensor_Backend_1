from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Float, Integer, String, create_engine, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


DATABASE_URL = "sqlite:///./masters.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Master(Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    specialization: Mapped[str] = mapped_column(String, nullable=False)


class ServiceDB(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    desc: Mapped[str] = mapped_column(String(100), nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)


Base.metadata.create_all(engine)


class Service:
    """Legacy service used by create_appointment."""

    def __init__(self, service_id: int, title: str):
        self.service_id = service_id
        self.title = title


legacy_services = [Service(1, "Стрижка")]

categories = [
    {"id": 1, "name": "Стрижки и укладки", "servicesCount": 5},
    {"id": 2, "name": "Маникюр и педикюр", "servicesCount": 5},
    {"id": 3, "name": "Брови и ресницы", "servicesCount": 4},
    {"id": 4, "name": "Спа-процедуры", "servicesCount": 4},
]


def seed_masters() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Master.id).limit(1)) is None:
            db.add_all(
                [
                    Master(id=1, name="Анна", specialization="Парикмахер"),
                    Master(id=2, name="Мария", specialization="Визажист"),
                ]
            )
            db.commit()


seed_masters()


def get_db():
    with SessionLocal() as db:
        yield db


def get_master(master_id: int) -> Master | None:
    with SessionLocal() as db:
        return db.get(Master, master_id)


def get_service(service_id: int) -> Service | None:
    return next(
        (service for service in legacy_services if service.service_id == service_id),
        None,
    )


class Appoinment:
    def __init__(
        self,
        appointment_id: int,
        client_name: str,
        master_id: int,
        service_id: int,
        time: str,
    ):
        self.id = appointment_id
        self.client_name = client_name
        self.master_id = master_id
        self.service_id = service_id
        self.time = time


appointments: list[Appoinment] = []


def create_appointment(
    client_name: str,
    master_id: int,
    service_id: int,
    time: str,
) -> Appoinment | None:
    if not client_name.strip() or not master_id or not service_id or not time.strip():
        return None

    master = get_master(master_id)
    service = get_service(service_id)
    if master is None or service is None:
        return None

    try:
        appointment_time = datetime.strptime(time, "%H:%M").time()
    except ValueError:
        return None

    opening_time = datetime.strptime("08:00", "%H:%M").time()
    closing_time = datetime.strptime("20:00", "%H:%M").time()
    if not opening_time <= appointment_time <= closing_time:
        return None

    if any(
        item.master_id == master_id and item.time == time for item in appointments
    ):
        return None

    appointment = Appoinment(
        appointment_id=len(appointments) + 1,
        client_name=client_name.strip(),
        master_id=master.id,
        service_id=service.service_id,
        time=time,
    )
    appointments.append(appointment)
    return appointment


class ServiceCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    category_id: int = Field(alias="categoryId")
    title: str = Field(max_length=100)
    desc: str = Field(max_length=100)
    duration: int = Field(ge=30, le=180)
    price: float = Field(gt=0)

    @field_validator("title", "desc")
    @classmethod
    def trim_and_require_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Field must not be empty")
        return trimmed


app = FastAPI()


@app.get("/masters")
def get_masters(
    specialization: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    statement = select(Master)
    if specialization is not None:
        statement = statement.where(Master.specialization == specialization)
    masters = db.scalars(statement.order_by(Master.id)).all()
    return [
        {
            "id": master.id,
            "name": master.name,
            "specialization": master.specialization,
        }
        for master in masters
    ]


@app.get("/masters/{master_id}")
def get_master_by_id(
    master_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    master = db.get(Master, master_id)
    if master is None:
        raise HTTPException(status_code=404, detail="Master not found")
    return {
        "id": master.id,
        "name": master.name,
        "specialization": master.specialization,
    }


@app.get("/categories")
def get_categories() -> list[dict[str, Any]]:
    return categories


@app.get("/categories/{category_id}")
def get_category(category_id: int) -> dict[str, Any]:
    category = next((item for item in categories if item["id"] == category_id), None)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@app.post("/services", status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    category = next(
        (item for item in categories if item["id"] == payload.category_id),
        None,
    )
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    service = ServiceDB(
        category_id=payload.category_id,
        title=payload.title,
        desc=payload.desc,
        duration=payload.duration,
        price=payload.price,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return {
        "id": service.id,
        "categoryId": service.category_id,
        "title": service.title,
        "desc": service.desc,
        "duration": service.duration,
        "price": service.price,
    }


def service_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(ServiceDB)) or 0)


def remove_test_services(db: Session, title: str) -> None:
    db.execute(delete(ServiceDB).where(ServiceDB.title == title))
    db.commit()


if __name__ == "__main__":
    client = TestClient(app)

    print("Проверка старых endpoint-ов:")
    response = client.get("/categories")
    assert response.status_code == 200 and len(response.json()) == 4
    print("GET /categories:", response.status_code, response.json())

    response = client.get("/categories/1")
    assert response.status_code == 200 and response.json()["id"] == 1
    print("GET /categories/1:", response.status_code, response.json())

    response = client.get("/categories/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Category not found"}
    print("GET /categories/999:", response.status_code, response.json())

    response = client.get("/masters")
    assert response.status_code == 200 and len(response.json()) >= 2
    print("GET /masters:", response.status_code, response.json())

    response = client.get("/masters?specialization=Парикмахер")
    assert response.status_code == 200
    assert all(
        item["specialization"] == "Парикмахер" for item in response.json()
    )
    print("GET /masters?specialization=Парикмахер:", response.status_code, response.json())

    response = client.get("/masters/1")
    assert response.status_code == 200 and response.json()["name"] == "Анна"
    print("GET /masters/1:", response.status_code, response.json())

    response = client.get("/masters/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Master not found"}
    print("GET /masters/999:", response.status_code, response.json())

    print("\nПроверка записей:")
    appointments.clear()
    first_appointment = create_appointment("Иванова А.А.", 1, 1, "10:00")
    second_appointment = create_appointment("Петрова А.А.", 1, 1, "11:00")
    assert first_appointment is not None and second_appointment is not None
    assert create_appointment("", 1, 1, "12:00") is None
    assert create_appointment("Сидорова А.А.", 1, 1, "00:00") is None
    assert len(appointments) == 2
    for appointment in appointments:
        print(appointment.client_name, appointment.time)

    print("\nПроверка POST /services:")
    test_title = "Тестовая укладка API"
    valid_payload = {
        "categoryId": 1,
        "title": "  Тестовая укладка API  ",
        "desc": "  Проверка сохранения в SQLite  ",
        "duration": 60,
        "price": 1500,
    }

    with SessionLocal() as db:
        remove_test_services(db, test_title)
        initial_count = service_count(db)

    response = client.post("/services", json=valid_payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] > 0
    assert created["categoryId"] == 1
    assert created["title"] == test_title
    assert created["desc"] == "Проверка сохранения в SQLite"
    print("Валидное тело:", response.status_code, created)

    with SessionLocal() as db:
        saved = db.get(ServiceDB, created["id"])
        assert saved is not None and saved.title == test_title
        assert service_count(db) == initial_count + 1
        remove_test_services(db, test_title)
        baseline_count = service_count(db)

    invalid_cases = [
        (
            "price строкой",
            {
                "categoryId": 1,
                "title": "Укладка",
                "desc": "Описание",
                "duration": 60,
                "price": "бесплатно",
            },
            422,
        ),
        (
            "несколько неверных полей",
            {
                "categoryId": 1,
                "title": "Укладка",
                "desc": "",
                "duration": 0,
                "price": -1500,
            },
            422,
        ),
        (
            "title из пробелов",
            {
                "categoryId": 1,
                "title": "   ",
                "desc": "Описание",
                "duration": 60,
                "price": 1000,
            },
            422,
        ),
        (
            "desc из пробелов",
            {
                "categoryId": 1,
                "title": "Укладка",
                "desc": "   ",
                "duration": 60,
                "price": 1000,
            },
            422,
        ),
        (
            "title длиннее 100",
            {
                "categoryId": 1,
                "title": "А" * 101,
                "desc": "Описание",
                "duration": 60,
                "price": 1000,
            },
            422,
        ),
        (
            "desc длиннее 100",
            {
                "categoryId": 1,
                "title": "Укладка",
                "desc": "Б" * 101,
                "duration": 60,
                "price": 1000,
            },
            422,
        ),
        (
            "duration больше 180",
            {
                "categoryId": 1,
                "title": "Укладка",
                "desc": "Описание",
                "duration": 181,
                "price": 1000,
            },
            422,
        ),
        (
            "price равна 0",
            {
                "categoryId": 1,
                "title": "Укладка",
                "desc": "Описание",
                "duration": 60,
                "price": 0,
            },
            422,
        ),
        (
            "неизвестная категория",
            {
                "categoryId": 999,
                "title": "Укладка",
                "desc": "Описание",
                "duration": 60,
                "price": 1000,
            },
            404,
        ),
    ]

    for label, payload, expected_status in invalid_cases:
        response = client.post("/services", json=payload)
        assert response.status_code == expected_status
        if expected_status == 404:
            assert response.json() == {"detail": "Category not found"}
        with SessionLocal() as db:
            assert service_count(db) == baseline_count
        print(label + ":", response.status_code, response.json())

    print("\nВсе проверки успешно пройдены.")
