from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from app_config import AppConfig
from datetime import datetime

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    order_uid = Column(String, unique=True, index=True)
    raw_data = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)

class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True)
    nm_id = Column(Integer, unique=True, index=True)
    raw_data = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)

def init_db(config: AppConfig):
    engine = create_engine(config.database_url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, DateTime # Добавьте нужные типы
# Импортируйте конфиг. Путь может быть другим (например, from config import AppConfig)
from app_config import AppConfig 

# 1. Инициализация конфига
config = AppConfig()

# 2. Создание движка БД
# Для SQLite в SQLAlchemy обязательно нужен аргумент check_same_thread=False
engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False},
    echo=False, # Можно поставить True, если нужно видеть SQL-запросы в консоли
)

# 3. Создание фабрики сессий (Именно этого объекта не хватало!)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Базовый класс для моделей
Base = declarative_base()

# 5. Определение моделей (Order и Card), которые также импортируются в fetchers.py
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    # ... добавьте остальные поля вашей модели ...

class Card(Base):
    __tablename__ = "cards"
    id = Column(Integer, primary_key=True, index=True)
    # ... добавьте остальные поля вашей модели ...

# 6. Создание таблиц в базе данных (если их еще нет)
# Эту строку часто выносят в отдельный скрипт инициализации или вызывают при старте сервиса
Base.metadata.create_all(bind=engine)

# Вспомогательная функция для получения сессии (генератор)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()