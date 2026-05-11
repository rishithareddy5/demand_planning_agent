import os
import sys
import types
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('POSTGRES_DB', 'testdb')
os.environ.setdefault('POSTGRES_USER', 'test')
os.environ.setdefault('POSTGRES_PASSWORD', 'test')
os.environ.setdefault('EMAIL_ADDRESS', 'sender@example.com')
os.environ.setdefault('EMAIL_APP_PASSWORD', 'pw')
os.environ.setdefault('SMTP_SERVER', 'smtp.example.com')
os.environ.setdefault('SMTP_PORT', '465')

# ---- optional external dependency stubs ----
if 'psycopg2' not in sys.modules:
    m = types.ModuleType('psycopg2')
    def connect(*args, **kwargs):
        raise RuntimeError('psycopg2.connect should be mocked in tests')
    m.connect = connect
    sys.modules['psycopg2'] = m

if 'sqlalchemy' not in sys.modules:
    sa = types.ModuleType('sqlalchemy')
    orm = types.ModuleType('sqlalchemy.orm')
    class DummyColumn:
        def __init__(self, *args, **kwargs): pass
        def __eq__(self, other): return ('eq', other)
    def Column(*args, **kwargs): return DummyColumn()
    def create_engine(*args, **kwargs): return MagicMock(name='engine')
    def sessionmaker(*args, **kwargs):
        class DummySession:
            def close(self): pass
        return lambda: DummySession()
    def declarative_base():
        class Base:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
        return Base
    class Session: pass
    sa.Column = Column
    sa.Integer = int
    sa.String = lambda *args, **kwargs: str
    sa.Numeric = float
    sa.Date = object
    sa.create_engine = create_engine
    orm.declarative_base = declarative_base
    orm.sessionmaker = sessionmaker
    orm.Session = Session
    sys.modules['sqlalchemy'] = sa
    sys.modules['sqlalchemy.orm'] = orm

if 'confluent_kafka' not in sys.modules:
    m = types.ModuleType('confluent_kafka')
    class Producer:
        def __init__(self, *args, **kwargs): pass
        def produce(self, *args, **kwargs): pass
        def flush(self, *args, **kwargs): pass
    class Consumer:
        def __init__(self, *args, **kwargs): pass
        def subscribe(self, *args, **kwargs): pass
        def poll(self, *args, **kwargs): return None
        def close(self): pass
    m.Producer = Producer
    m.Consumer = Consumer
    class KafkaError(Exception): pass
    m.KafkaError = KafkaError
    sys.modules['confluent_kafka'] = m

if 'falkordb' not in sys.modules:
    m = types.ModuleType('falkordb')
    class FalkorDB:
        def __init__(self, *args, **kwargs): pass
        def select_graph(self, *args, **kwargs): return self
        def query(self, *args, **kwargs):
            result = MagicMock()
            result.result_set = []
            return result
    m.FalkorDB = FalkorDB
    sys.modules['falkordb'] = m

if 'temporalio' not in sys.modules:
    temporalio = types.ModuleType('temporalio')
    activity_mod = types.ModuleType('temporalio.activity')
    workflow_mod = types.ModuleType('temporalio.workflow')
    client_mod = types.ModuleType('temporalio.client')
    worker_mod = types.ModuleType('temporalio.worker')

    def defn(fn=None, *args, **kwargs):
        if fn is None:
            return lambda f: f
        return fn
    activity_mod.defn = defn
    workflow_mod.defn = defn
    workflow_mod.run = defn
    workflow_mod.signal = defn
    workflow_mod.logger = MagicMock()
    workflow_mod.execute_activity = MagicMock()
    workflow_mod.wait_condition = MagicMock()
    class _Unsafe:
        def imports_passed_through(self):
            class CM:
                def __enter__(self): return None
                def __exit__(self, *args): return False
            return CM()
    workflow_mod.unsafe = _Unsafe()

    class Client:
        @classmethod
        async def connect(cls, *args, **kwargs): return cls()
        def get_workflow_handle(self, *args, **kwargs): return self
        async def signal(self, *args, **kwargs): pass
    class Worker:
        def __init__(self, *args, **kwargs): pass
        async def run(self): pass
    client_mod.Client = Client
    worker_mod.Worker = Worker
    temporalio.activity = activity_mod
    temporalio.workflow = workflow_mod
    temporalio.client = client_mod
    temporalio.worker = worker_mod
    sys.modules['temporalio'] = temporalio
    sys.modules['temporalio.activity'] = activity_mod
    sys.modules['temporalio.workflow'] = workflow_mod
    sys.modules['temporalio.client'] = client_mod
    sys.modules['temporalio.worker'] = worker_mod

import pytest
import pandas as pd

@pytest.fixture(autouse=True)
def stable_sku_master(monkeypatch):
    sku_map = {
        'malkist cheese 48 pcs x 72': 'SKU01',
        'malkist cheese  48 pcs x 72': 'SKU01',
        'beng beng wafer 22gm': 'SKU04',
        'kopiko cappuccino': 'SKU08',
    }
    sku_names = list(sku_map.keys())
    sku_id_to_name = {
        'SKU01': 'MALKIST CHEESE  48 PCS X 72',
        'SKU04': 'BENG BENG WAFER 22GM',
        'SKU08': 'KOPIKO CAPPUCCINO',
    }
    for target in [
        'app.data.sku_data',
        'app.services.reply_parser_service',
        'app.services.attachment_parser_service',
    ]:
        monkeypatch.setattr(f'{target}.get_sku_map', lambda: sku_map, raising=False)
        monkeypatch.setattr(f'{target}.get_sku_names', lambda: sku_names, raising=False)
        monkeypatch.setattr(f'{target}.get_sku_id_to_name', lambda: sku_id_to_name, raising=False)

@pytest.fixture
def distributor_map():
    return {
        'revanbejagam@gmail.com': 'D01',
        'rishithareddyc2002@gmail.com': 'D02',
        'saherwardi.mustafa@gmail.com': 'D03',
        'lingaphani21@gmail.com': 'D04',
        'poojithak493@gmail.com': 'D05',
    }

@pytest.fixture
def valid_primary_sales_df():
    return pd.DataFrame({
        'Transaction Date': ['2024-01-15', '2024-02-20'],
        'Distributor ID': ['D01', 'D02'],
        'SKU ID': ['SKU01', 'SKU04'],
        'SKU Name': ['MALKIST CHEESE  48 PCS X 72', 'BENG BENG WAFER 22GM'],
        'Gross Dispatch Value': [1200.0, 800.0],
        'Opening Stock Quantity': [500, 300],
        'Remaining Quantity': [200, 100],
        'Priority Flag': ['high', 'medium'],
        'Product Category Snapshot': ['Crackers', 'Wafers'],
        'Distribution Channel Type': ['GT', 'MT'],
        'Distributor Priority Tier': ['Tier1', 'Tier2'],
        'Mapping Status': ['Mapped', 'Unmapped'],
    })

@pytest.fixture
def mock_smtp_server():
    with patch('smtplib.SMTP_SSL') as mock_smtp:
        server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = server
        mock_smtp.return_value.__exit__.return_value = False
        yield mock_smtp, server
