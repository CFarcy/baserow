import pytest

from baserow.contrib.database.fields.dependencies.exceptions import (
    CircularFieldDependencyError,
)
from baserow.contrib.database.fields.dependencies.handler import FieldDependencyHandler
from baserow.contrib.database.fields.dependencies.models import FieldDependency
from baserow.contrib.database.fields.field_cache import FieldCache


def _unwrap_ids(qs):
    return list(qs.values_list("id", flat=True))


@pytest.mark.django_db
def test_formula_fields_will_be_rebuilt_to_depend_on_each_other(
    api_client, data_fixture, django_assert_num_queries
):
    first_formula_field = data_fixture.create_formula_field(
        name="first", formula_type="text", formula='"a"'
    )
    dependant_formula = data_fixture.create_formula_field(
        name="second",
        table=first_formula_field.table,
        formula_type="text",
        formula="field('first')",
    )

    cache = FieldCache()
    FieldDependencyHandler.rebuild_dependencies(dependant_formula, cache)

    assert _unwrap_ids(dependant_formula.field_dependencies) == [first_formula_field.id]
    assert _unwrap_ids(dependant_formula.dependant_fields) == []

    assert _unwrap_ids(first_formula_field.field_dependencies) == []
    assert _unwrap_ids(first_formula_field.dependant_fields) == [dependant_formula.id]

    _assert_rebuilding_changes_nothing(cache, dependant_formula)


def _assert_rebuilding_changes_nothing(cache, field_to_rebuild):
    before_ids = list(
        FieldDependency.objects.order_by("id").values_list("id", flat=True)
    )
    before_strs = [str(f) for f in FieldDependency.objects.order_by("id").all()]
    # Rebuilding a second time doesn't change any field dependency rows
    FieldDependencyHandler.rebuild_dependencies(field_to_rebuild, cache)
    after_ids = list(
        FieldDependency.objects.order_by("id").values_list("id", flat=True)
    )
    after_strs = [str(f) for f in FieldDependency.objects.order_by("id").all()]
    assert before_ids == after_ids
    assert before_strs == after_strs


@pytest.mark.django_db
def test_rebuilding_with_a_circular_ref_will_raise(
    api_client, data_fixture, django_assert_num_queries
):
    first_formula_field = data_fixture.create_formula_field(
        name="first", formula_type="text", formula='field("second")'
    )
    second_formula_field = data_fixture.create_formula_field(
        name="second",
        table=first_formula_field.table,
        formula_type="text",
        formula="field('first')",
    )

    cache = FieldCache()
    FieldDependencyHandler.rebuild_dependencies(first_formula_field, cache)
    with pytest.raises(CircularFieldDependencyError):
        FieldDependencyHandler.rebuild_dependencies(second_formula_field, cache)

    assert _unwrap_ids(second_formula_field.field_dependencies) == []
    assert _unwrap_ids(second_formula_field.dependant_fields) == [
        first_formula_field.id
    ]

    assert _unwrap_ids(first_formula_field.field_dependencies) == [
        second_formula_field.id
    ]
    assert _unwrap_ids(first_formula_field.dependant_fields) == []


@pytest.mark.django_db
def test_rebuilding_a_link_row_field_creates_dependencies_with_vias(
    api_client, data_fixture, django_assert_num_queries
):
    table = data_fixture.create_database_table()
    other_table = data_fixture.create_database_table()
    data_fixture.create_text_field(primary=True, name="primary", table=table)
    other_primary_field = data_fixture.create_text_field(
        primary=True, name="primary", table=other_table
    )
    link_row_field = data_fixture.create_link_row_field(
        name="link", table=table, link_row_table=other_table
    )

    cache = FieldCache()
    FieldDependencyHandler.rebuild_dependencies(link_row_field, cache)

    assert _unwrap_ids(link_row_field.field_dependencies) == [other_primary_field.id]
    assert _unwrap_ids(link_row_field.dependant_fields) == []
    assert link_row_field.vias.count() == 1
    via = link_row_field.vias.get()
    assert via.dependency.id == other_primary_field.id
    assert via.dependant.id == link_row_field.id
    assert via.via.id == link_row_field.id

    _assert_rebuilding_changes_nothing(cache, link_row_field)


@pytest.mark.django_db
def test_trashing_a_link_row_field_breaks_vias(
    api_client, data_fixture, django_assert_num_queries
):
    table = data_fixture.create_database_table()
    other_table = data_fixture.create_database_table()
    data_fixture.create_text_field(primary=True, name="primary", table=table)
    field = data_fixture.create_text_field(name="field", table=table)
    other_primary_field = data_fixture.create_text_field(
        primary=True, name="primary", table=other_table
    )
    link_row_field = data_fixture.create_link_row_field(
        name="link", table=table, link_row_table=other_table
    )

    cache = FieldCache()
    FieldDependencyHandler.rebuild_dependencies(link_row_field, cache)

    # Create a fake dependencies until we have lookup fields
    via_dep = FieldDependency.objects.create(
        dependency=other_primary_field, via=link_row_field, dependant=field
    )
    direct_dep = FieldDependency.objects.create(
        dependency=link_row_field, dependant=field
    )

    link_row_field.trashed = True
    link_row_field.save()
    FieldDependencyHandler.rebuild_dependencies(link_row_field, cache)

    # The trashed field is no longer part of the graph
    assert not link_row_field.dependencies.exists()
    assert not link_row_field.vias.exists()
    assert not link_row_field.dependants.exists()

    # The dep that went via the trashed field has been broken
    via_dep.refresh_from_db()
    assert via_dep.dependency is None
    assert via_dep.broken_reference_field_name == "link"
    assert via_dep.via is None

    direct_dep.refresh_from_db()
    assert direct_dep.dependency is None
    assert direct_dep.broken_reference_field_name == "link"
    assert direct_dep.via is None

    _assert_rebuilding_changes_nothing(cache, link_row_field)


@pytest.mark.django_db
def test_str_of_field_dependency_uniquely_identifies_it(
    api_client, data_fixture, django_assert_num_queries
):
    table = data_fixture.create_database_table()
    table_b = data_fixture.create_database_table()
    field_a = data_fixture.create_text_field(primary=True, name="a", table=table)
    field_b = data_fixture.create_text_field(name="b", table=table)

    via_field = data_fixture.create_link_row_field(
        name="via", table=table, link_row_table=table_b
    )
    other_via_field = data_fixture.create_link_row_field(
        name="other_via", table=table, link_row_table=table_b
    )
    first_a_to_b = FieldDependency(dependant=field_a, dependency=field_b)
    second_a_to_b = FieldDependency(dependant=field_a, dependency=field_b)
    with django_assert_num_queries(0):
        assert str(first_a_to_b) == str(second_a_to_b)
    # Saving so they have id's should still return the same strings even though they
    # have different ids now
    first_a_to_b.save()
    second_a_to_b.save()
    assert first_a_to_b.id != second_a_to_b.id
    with django_assert_num_queries(0):
        assert str(first_a_to_b) == str(second_a_to_b)

        assert str(FieldDependency(dependant=field_a, dependency=field_b)) != str(
            FieldDependency(dependant=field_b, dependency=field_a)
        )

        # If all the same with a via field
        assert str(
            FieldDependency(dependant=field_a, via=via_field, dependency=field_b)
        ) == str(FieldDependency(dependant=field_a, via=via_field, dependency=field_b))
        # If one doesn't have a via
        assert str(
            FieldDependency(dependant=field_a, via=via_field, dependency=field_b)
        ) != str(FieldDependency(dependant=field_a, dependency=field_b))
        # If the vias differ then
        assert str(
            FieldDependency(dependant=field_a, via=via_field, dependency=field_b)
        ) != str(
            FieldDependency(dependant=field_a, via=other_via_field, dependency=field_b)
        )

        # Normal broken refs
        assert str(
            FieldDependency(dependant=field_a, broken_reference_field_name="b")
        ) == str(FieldDependency(dependant=field_a, broken_reference_field_name="b"))
        # Different broken ref
        assert str(
            FieldDependency(dependant=field_a, broken_reference_field_name="b")
        ) != str(FieldDependency(dependant=field_a, broken_reference_field_name="c"))
        # Different dependant
        assert str(
            FieldDependency(dependant=field_a, broken_reference_field_name="b")
        ) != str(FieldDependency(dependant=field_b, broken_reference_field_name="b"))

        # Via broken refs
        assert str(
            FieldDependency(
                dependant=field_a, via=via_field, broken_reference_field_name="via"
            )
        ) == str(
            FieldDependency(
                dependant=field_a,
                via=via_field,
                broken_reference_field_name="via",
            )
        )
        # Different via same broken
        assert str(
            FieldDependency(
                dependant=field_a, via=via_field, broken_reference_field_name="via"
            )
        ) != str(
            FieldDependency(
                dependant=field_a,
                via=other_via_field,
                broken_reference_field_name="via",
            )
        )
        # Same via different broken
        assert str(
            FieldDependency(
                dependant=field_a, via=via_field, broken_reference_field_name="via"
            )
        ) != str(
            FieldDependency(
                dependant=field_a,
                via=via_field,
                broken_reference_field_name="other",
            )
        )
        # Same via same broken different dependant
        assert str(
            FieldDependency(
                dependant=field_a, via=via_field, broken_reference_field_name="via"
            )
        ) != str(
            FieldDependency(
                dependant=field_b,
                via=via_field,
                broken_reference_field_name="via",
            )
        )
