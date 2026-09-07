from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.sql.sqltypes import String
from .config import settings

@compiles(String, "mysql")
def compile_mysql_string(type_: String, compiler, **kwargs):
    """MySQL requires a length for VARCHAR; legacy models used portable unbounded String."""
    if type_.length is None:
        return "VARCHAR(255)"
    return compiler.visit_VARCHAR(type_, **kwargs)

class Base(DeclarativeBase): pass
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
