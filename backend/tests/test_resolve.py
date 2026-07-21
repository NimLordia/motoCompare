from app.catalog import service


def _seed_variants(make_bike):
    return {
        "r7": make_bike(manufacturer="Yamaha", model="YZF-R7", year=2023, market="EU"),
        "mt07": make_bike(manufacturer="Yamaha", model="MT-07", year=2023, market="EU"),
        "panigale": make_bike(manufacturer="Ducati", model="Panigale V4", year=2023, market="EU"),
        "zx6r": make_bike(manufacturer="Kawasaki", model="Ninja ZX-6R", year=2024, market="US"),
    }


def test_short_alias_resolves_hyphenated_model(db, make_bike):
    bikes = _seed_variants(make_bike)
    candidates = service.resolve_bike(db, "R7")

    assert candidates
    assert candidates[0].bike.id == bikes["r7"].id
    assert candidates[0].confidence == 1.0


def test_manufacturer_plus_model_ranks_exact_match_first(db, make_bike):
    bikes = _seed_variants(make_bike)
    candidates = service.resolve_bike(db, "yamaha r7")

    assert candidates[0].bike.id == bikes["r7"].id
    assert all(candidate.confidence <= candidates[0].confidence for candidate in candidates)


def test_partial_model_name_matches(db, make_bike):
    bikes = _seed_variants(make_bike)
    candidates = service.resolve_bike(db, "panigale")

    assert candidates[0].bike.id == bikes["panigale"].id


def test_year_token_participates_in_ranking(db, make_bike):
    make_bike(manufacturer="Yamaha", model="MT-07", year=2021, market="EU")
    bikes = _seed_variants(make_bike)
    candidates = service.resolve_bike(db, "mt 07 2023")

    assert candidates[0].bike.id == bikes["mt07"].id


def test_market_filter_excludes_other_markets(db, make_bike):
    _seed_variants(make_bike)
    candidates = service.resolve_bike(db, "R7", market="US")

    assert candidates == []


def test_market_filter_keeps_unspecified_market(db, make_bike):
    bike = make_bike(manufacturer="Yamaha", model="YZF-R7", year=2022, market="")
    candidates = service.resolve_bike(db, "R7", market="US")

    assert [candidate.bike.id for candidate in candidates] == [bike.id]


def test_empty_and_gibberish_queries_return_nothing(db, make_bike):
    _seed_variants(make_bike)
    assert service.resolve_bike(db, "   ") == []
    assert service.resolve_bike(db, "qzxwv") == []


def test_limit_caps_results(db, make_bike):
    for year in range(2015, 2024):
        make_bike(manufacturer="Yamaha", model="MT-07", year=year, market="EU")
    candidates = service.resolve_bike(db, "yamaha mt-07", limit=3)

    assert len(candidates) == 3
    years = [candidate.bike.year for candidate in candidates]
    assert years == sorted(years, reverse=True)
