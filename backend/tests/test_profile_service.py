import pytest

from app.catalog.service import CatalogNotFoundError
from app.profile import service
from app.profile.models import DEFAULT_USER_ID
from app.profile.service import ProfileNotFoundError, ProfileValidationError


def test_get_profile_returns_defaults_before_any_write(db):
    profile = service.get_profile(db, DEFAULT_USER_ID)

    assert profile.unit_system == "metric"
    assert profile.market is None
    assert profile.riding_style is None
    assert profile.priority_factors == []
    assert profile.current_bike is None


def test_update_profile_round_trip(db):
    service.update_profile(
        db,
        DEFAULT_USER_ID,
        unit_system="mixed",
        market="EU",
        riding_style="sport touring",
        priority_factors=["heat", "comfort", "cost"],
    )

    profile = service.get_profile(db, DEFAULT_USER_ID)

    assert profile.unit_system == "mixed"
    assert profile.market == "EU"
    assert profile.riding_style == "sport touring"
    assert profile.priority_factors == ["heat", "comfort", "cost"]


def test_update_profile_is_a_full_replace(db):
    service.update_profile(
        db, DEFAULT_USER_ID, unit_system="imperial", market="US", priority_factors=["heat"]
    )

    service.update_profile(db, DEFAULT_USER_ID, unit_system="metric")

    profile = service.get_profile(db, DEFAULT_USER_ID)
    assert profile.unit_system == "metric"
    assert profile.market is None
    assert profile.priority_factors == []


def test_update_profile_strips_and_blanks_to_none(db):
    profile = service.update_profile(
        db,
        DEFAULT_USER_ID,
        unit_system="metric",
        market="  EU ",
        riding_style="   ",
        priority_factors=[" heat "],
    )

    assert profile.market == "EU"
    assert profile.riding_style is None
    assert profile.priority_factors == ["heat"]


def test_update_profile_rejects_unknown_unit_system(db):
    with pytest.raises(ProfileValidationError, match="unknown unit system"):
        service.update_profile(db, DEFAULT_USER_ID, unit_system="nautical")


def test_update_profile_rejects_blank_priority_factor(db):
    with pytest.raises(ProfileValidationError, match="non-empty"):
        service.update_profile(
            db, DEFAULT_USER_ID, unit_system="metric", priority_factors=["heat", "  "]
        )


def test_update_profile_rejects_repeated_priority_factors(db):
    with pytest.raises(ProfileValidationError, match="repeat"):
        service.update_profile(
            db, DEFAULT_USER_ID, unit_system="metric", priority_factors=["heat", "Heat"]
        )


def test_first_garage_bike_becomes_current(db, make_bike):
    bike = make_bike()

    added = service.add_garage_bike(db, DEFAULT_USER_ID, bike.id, nickname="track day")

    assert added.is_current is True
    assert added.nickname == "track day"
    assert added.bike.display_name == "Yamaha YZF-R7 2023 (EU)"


def test_second_garage_bike_is_not_current(db, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    service.add_garage_bike(db, DEFAULT_USER_ID, first.id)

    added = service.add_garage_bike(db, DEFAULT_USER_ID, second.id)

    assert added.is_current is False


def test_repeat_garage_add_upserts_nickname(db, make_bike):
    bike = make_bike()
    first = service.add_garage_bike(db, DEFAULT_USER_ID, bike.id, nickname="old name")

    second = service.add_garage_bike(db, DEFAULT_USER_ID, bike.id, nickname="new name")

    assert second.id == first.id
    assert second.nickname == "new name"
    assert second.is_current is True
    assert len(service.list_garage(db, DEFAULT_USER_ID)) == 1


def test_garage_add_unknown_bike_raises_not_found(db):
    with pytest.raises(CatalogNotFoundError):
        service.add_garage_bike(db, DEFAULT_USER_ID, 424242)


def test_set_current_switches_exclusively(db, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    service.add_garage_bike(db, DEFAULT_USER_ID, first.id)
    second_row = service.add_garage_bike(db, DEFAULT_USER_ID, second.id)

    service.set_current_garage_bike(db, DEFAULT_USER_ID, second_row.id)

    garage = service.list_garage(db, DEFAULT_USER_ID)
    current_flags = {entry.bike.id: entry.is_current for entry in garage}
    assert current_flags == {first.id: False, second.id: True}


def test_set_current_unknown_id_raises(db):
    with pytest.raises(ProfileNotFoundError):
        service.set_current_garage_bike(db, DEFAULT_USER_ID, 424242)


def test_removing_current_bike_promotes_most_recent_remaining(db, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    third = make_bike(model="Tenere 700")
    current_row = service.add_garage_bike(db, DEFAULT_USER_ID, first.id)
    service.add_garage_bike(db, DEFAULT_USER_ID, second.id)
    service.add_garage_bike(db, DEFAULT_USER_ID, third.id)

    service.remove_garage_bike(db, DEFAULT_USER_ID, current_row.id)

    garage = service.list_garage(db, DEFAULT_USER_ID)
    current_flags = {entry.bike.id: entry.is_current for entry in garage}
    assert current_flags == {second.id: False, third.id: True}


def test_removing_noncurrent_bike_keeps_current(db, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    service.add_garage_bike(db, DEFAULT_USER_ID, first.id)
    second_row = service.add_garage_bike(db, DEFAULT_USER_ID, second.id)

    service.remove_garage_bike(db, DEFAULT_USER_ID, second_row.id)

    (remaining,) = service.list_garage(db, DEFAULT_USER_ID)
    assert remaining.bike.id == first.id
    assert remaining.is_current is True


def test_removing_last_garage_bike_leaves_no_current(db, make_bike):
    bike = make_bike()
    row = service.add_garage_bike(db, DEFAULT_USER_ID, bike.id)

    service.remove_garage_bike(db, DEFAULT_USER_ID, row.id)

    assert service.list_garage(db, DEFAULT_USER_ID) == []
    assert service.get_profile(db, DEFAULT_USER_ID).current_bike is None


def test_remove_unknown_garage_bike_raises(db):
    with pytest.raises(ProfileNotFoundError):
        service.remove_garage_bike(db, DEFAULT_USER_ID, 424242)


def test_garage_list_puts_current_first(db, make_bike):
    first = make_bike()
    second = make_bike(model="MT-07")
    service.add_garage_bike(db, DEFAULT_USER_ID, first.id)
    service.add_garage_bike(db, DEFAULT_USER_ID, second.id)

    garage = service.list_garage(db, DEFAULT_USER_ID)

    assert garage[0].bike.id == first.id
    assert garage[0].is_current is True


def test_profile_reports_current_bike(db, make_bike):
    bike = make_bike()
    service.add_garage_bike(db, DEFAULT_USER_ID, bike.id)

    profile = service.get_profile(db, DEFAULT_USER_ID)

    assert profile.current_bike is not None
    assert profile.current_bike.id == bike.id
    assert profile.current_bike.display_name == "Yamaha YZF-R7 2023 (EU)"


def test_dream_bike_round_trip(db, make_bike):
    bike = make_bike(manufacturer="Ducati", model="Panigale V4")

    added = service.add_dream_bike(db, DEFAULT_USER_ID, bike.id, note="someday")
    (listed,) = service.list_dream_bikes(db, DEFAULT_USER_ID)

    assert listed.id == added.id
    assert listed.note == "someday"
    assert listed.bike.display_name == "Ducati Panigale V4 2023 (EU)"


def test_repeat_dream_add_upserts_note(db, make_bike):
    bike = make_bike(manufacturer="Ducati", model="Panigale V4")
    first = service.add_dream_bike(db, DEFAULT_USER_ID, bike.id, note="someday")

    second = service.add_dream_bike(db, DEFAULT_USER_ID, bike.id, note="after the track course")

    assert second.id == first.id
    assert second.note == "after the track course"
    assert len(service.list_dream_bikes(db, DEFAULT_USER_ID)) == 1


def test_remove_dream_bike(db, make_bike):
    bike = make_bike(manufacturer="Ducati", model="Panigale V4")
    added = service.add_dream_bike(db, DEFAULT_USER_ID, bike.id)

    service.remove_dream_bike(db, DEFAULT_USER_ID, added.id)

    assert service.list_dream_bikes(db, DEFAULT_USER_ID) == []


def test_remove_unknown_dream_bike_raises(db):
    with pytest.raises(ProfileNotFoundError):
        service.remove_dream_bike(db, DEFAULT_USER_ID, 424242)
