"""Tests for customer and job record repositories."""

from phoenix_office.models.records import CustomerRecord, JobRecord
from phoenix_office.records.repository import InMemoryCustomerRepository, InMemoryJobRepository


def test_save_and_get_customer() -> None:
    """It should save and retrieve a customer record."""
    repo = InMemoryCustomerRepository()
    record = CustomerRecord(customer_id="c1", display_name="Abby Hill")
    repo.save_customer(record)

    retrieved = repo.get_customer("c1")
    assert retrieved is not None
    assert retrieved.customer_id == "c1"
    assert retrieved.display_name == "Abby Hill"


def test_get_missing_customer_returns_none() -> None:
    """It should return None when a customer is not found."""
    repo = InMemoryCustomerRepository()
    assert repo.get_customer("missing") is None


def test_saving_same_customer_id_overwrites() -> None:
    """Saving a customer with an existing ID should overwrite the old record."""
    repo = InMemoryCustomerRepository()
    record1 = CustomerRecord(customer_id="c1", display_name="Abby Hill")
    record2 = CustomerRecord(customer_id="c1", display_name="Abigail Hill")

    repo.save_customer(record1)
    repo.save_customer(record2)

    retrieved = repo.get_customer("c1")
    assert retrieved is not None
    assert retrieved.display_name == "Abigail Hill"
    assert len(repo.list_customers()) == 1


def test_list_customers_preserves_insertion_order() -> None:
    """list_customers should return records in the order they were first saved."""
    repo = InMemoryCustomerRepository()
    record1 = CustomerRecord(customer_id="c1", display_name="First")
    record2 = CustomerRecord(customer_id="c2", display_name="Second")
    record3 = CustomerRecord(customer_id="c3", display_name="Third")

    repo.save_customer(record1)
    repo.save_customer(record2)
    repo.save_customer(record3)

    # Update c2 to ensure insertion order is maintained, not update order
    # (dicts maintain insertion order even when value is updated)
    record2_updated = CustomerRecord(customer_id="c2", display_name="Second Updated")
    repo.save_customer(record2_updated)

    customers = repo.list_customers()
    assert len(customers) == 3
    assert customers[0].customer_id == "c1"
    assert customers[1].customer_id == "c2"
    assert customers[1].display_name == "Second Updated"
    assert customers[2].customer_id == "c3"


def test_save_and_get_job() -> None:
    """It should save and retrieve a job record."""
    repo = InMemoryJobRepository()
    record = JobRecord(
        job_id="j1",
        customer_id="c1",
        job_name="Tank Removal",
        site_street_address="123 Main St",
        site_city_state_zip="Anytown, ST 12345",
    )
    repo.save_job(record)

    retrieved = repo.get_job("j1")
    assert retrieved is not None
    assert retrieved.job_id == "j1"
    assert retrieved.job_name == "Tank Removal"


def test_get_missing_job_returns_none() -> None:
    """It should return None when a job is not found."""
    repo = InMemoryJobRepository()
    assert repo.get_job("missing") is None


def test_saving_same_job_id_overwrites() -> None:
    """Saving a job with an existing ID should overwrite the old record."""
    repo = InMemoryJobRepository()
    record1 = JobRecord(
        job_id="j1",
        customer_id="c1",
        job_name="Tank Removal",
        site_street_address="123 Main St",
        site_city_state_zip="Anytown, ST 12345",
    )
    record2 = JobRecord(
        job_id="j1",
        customer_id="c1",
        job_name="Tank Removal Updated",
        site_street_address="123 Main St",
        site_city_state_zip="Anytown, ST 12345",
    )

    repo.save_job(record1)
    repo.save_job(record2)

    retrieved = repo.get_job("j1")
    assert retrieved is not None
    assert retrieved.job_name == "Tank Removal Updated"
    assert len(repo.list_jobs()) == 1


def test_list_jobs_preserves_insertion_order() -> None:
    """list_jobs should return records in the order they were first saved."""
    repo = InMemoryJobRepository()
    record1 = JobRecord(
        job_id="j1", customer_id="c1", job_name="Job 1",
        site_street_address="1", site_city_state_zip="1"
    )
    record2 = JobRecord(
        job_id="j2", customer_id="c2", job_name="Job 2",
        site_street_address="2", site_city_state_zip="2"
    )
    record3 = JobRecord(
        job_id="j3", customer_id="c1", job_name="Job 3",
        site_street_address="3", site_city_state_zip="3"
    )

    repo.save_job(record1)
    repo.save_job(record2)
    repo.save_job(record3)

    jobs = repo.list_jobs()
    assert len(jobs) == 3
    assert jobs[0].job_id == "j1"
    assert jobs[1].job_id == "j2"
    assert jobs[2].job_id == "j3"


def test_list_jobs_for_customer_filters_and_preserves_order() -> None:
    """list_jobs_for_customer should filter by customer_id and maintain insertion order."""
    repo = InMemoryJobRepository()
    record1 = JobRecord(
        job_id="j1", customer_id="c1", job_name="Job 1",
        site_street_address="1", site_city_state_zip="1"
    )
    record2 = JobRecord(
        job_id="j2", customer_id="c2", job_name="Job 2",
        site_street_address="2", site_city_state_zip="2"
    )
    record3 = JobRecord(
        job_id="j3", customer_id="c1", job_name="Job 3",
        site_street_address="3", site_city_state_zip="3"
    )
    record4 = JobRecord(
        job_id="j4", customer_id="c1", job_name="Job 4",
        site_street_address="4", site_city_state_zip="4"
    )

    repo.save_job(record1)
    repo.save_job(record2)
    repo.save_job(record3)
    repo.save_job(record4)

    c1_jobs = repo.list_jobs_for_customer("c1")
    assert len(c1_jobs) == 3
    assert c1_jobs[0].job_id == "j1"
    assert c1_jobs[1].job_id == "j3"
    assert c1_jobs[2].job_id == "j4"

    c2_jobs = repo.list_jobs_for_customer("c2")
    assert len(c2_jobs) == 1
    assert c2_jobs[0].job_id == "j2"

    c3_jobs = repo.list_jobs_for_customer("missing")
    assert len(c3_jobs) == 0
