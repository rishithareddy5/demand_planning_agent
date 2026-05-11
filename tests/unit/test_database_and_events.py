import importlib
import json
from datetime import date
from unittest.mock import MagicMock


def test_database_get_db_closes_session(monkeypatch):
    import app.core.database as db
    session = MagicMock()
    monkeypatch.setattr(db, 'SessionLocal', lambda: session)
    gen = db.get_db()
    assert next(gen) is session
    try:
        next(gen)
    except StopIteration:
        pass
    session.close.assert_called_once()


def test_database_get_connection_calls_psycopg(monkeypatch):
    import app.core.database as db
    mock_connect = MagicMock(return_value='conn')
    monkeypatch.setattr(db.psycopg2, 'connect', mock_connect)
    assert db.get_connection() == 'conn'
    mock_connect.assert_called_once()


def test_ensure_confirmed_demands_table_executes_ddl(monkeypatch):
    import app.core.database as db
    cur = MagicMock()
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    monkeypatch.setattr(db, 'get_connection', lambda: conn)
    db.ensure_confirmed_demands_table()
    assert 'CREATE TABLE IF NOT EXISTS confirmed_demands' in cur.execute.call_args.args[0]
    conn.close.assert_called_once()


def test_write_confirmed_qty_returns_row_id(monkeypatch):
    import app.core.database as db
    cur = MagicMock()
    cur.fetchone.return_value = [77]
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    monkeypatch.setattr(db, 'get_connection', lambda: conn)
    result = db.write_confirmed_qty('D01', 'SKU01', 40, 10, 10, 10, 10, None, 'valid', 5, cycle_date=date(2024, 1, 1))
    assert result == 77
    assert cur.execute.call_args.args[1]['confirmed_30d_qty'] == 40


def test_events_producers_emit_payloads(monkeypatch):
    import app.events.producers as producers
    fake = MagicMock()
    monkeypatch.setattr(producers, '_producer', fake)
    producers.emit_reply_received('D01', 9)
    producers.emit_demand_confirmed('D01', 300)
    assert fake.produce.call_count == 2
    payload = json.loads(fake.produce.call_args_list[1].kwargs['value'].decode())
    assert payload == {'distributor_id': 'D01', 'confirmed_qty': 300}


def test_consumer_processes_one_message_then_stops(monkeypatch):
    import app.events.consumers as consumers
    msg = MagicMock()
    msg.error.return_value = False
    msg.value.return_value = json.dumps({'distributor_id': 'D01', 'parsed_reply_id': 4}).encode()
    fake_consumer = MagicMock()
    fake_consumer.poll.side_effect = [msg, KeyboardInterrupt()]
    monkeypatch.setattr(consumers, 'get_consumer', lambda group: fake_consumer)
    handled = []
    import pytest
    with pytest.raises(KeyboardInterrupt):
        consumers.consume_reply_received(lambda d, rid: handled.append((d, rid)))
    assert handled == [('D01', 4)]
    fake_consumer.close.assert_called_once()
