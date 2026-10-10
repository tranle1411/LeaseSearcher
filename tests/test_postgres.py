from sqlalchemy.orm import Session

from backend.storage import Snapshot, engine_for, select_dataset


def test_postgres_round_trip_and_immutable_version(postgres_url, dataset):
    engine = engine_for(postgres_url)
    with Session(engine) as session, session.begin():
        prior = session.get(Snapshot, dataset.version)
        if prior:
            session.delete(prior)
            session.flush()
        session.add(Snapshot(version=dataset.version, payload=dataset.model_dump(mode="json")))
    restored, mode = select_dataset(dataset, engine)
    assert restored == dataset and mode == "postgresql"
    changed = dataset.model_copy(update={"collection_period": "different"})
    import pytest

    with pytest.raises(ValueError, match="differs"):
        select_dataset(changed, engine)
    with Session(engine) as session, session.begin():
        session.delete(session.get(Snapshot, dataset.version))
    engine.dispose()
