from io import BytesIO

import pytest
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_204_NO_CONTENT

from baserow.contrib.database.fields.handler import FieldHandler
from baserow.contrib.database.fields.registries import field_type_registry
from baserow.contrib.database.formula import (
    BaserowFormulaInvalidType,
    BaserowFormulaNumberType,
    BaserowFormulaArrayType,
)
from baserow.contrib.database.rows.handler import RowHandler
from baserow.core.handler import CoreHandler


@pytest.mark.django_db
def test_can_update_lookup_field_value(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(lookupfield=f"2021-02-01", primaryfield="primary a")
    b = table2_model.objects.create(lookupfield=f"2022-02-03", primaryfield="primary b")

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table2.id, "row_id": a.id},
        ),
        {f"field_{looked_up_field.id}": "2000-02-01"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2000-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_can_set_sub_type_options_for_lookup_field(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_number_field(
        name="lookupfield",
        table=table2,
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(lookupfield=1, primaryfield="primary a")
    b = table2_model.objects.create(lookupfield=2, primaryfield="primary b")

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
        number_decimal_places=2,
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "1.00"},
                    {"id": b.id, "value": "2.00"},
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_can_lookup_single_select(data_fixture, api_client, django_assert_num_queries):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_single_select_field(
        table=table2, name="lookupfield"
    )
    option_a = data_fixture.create_select_option(
        field=looked_up_field, value="A", color="blue"
    )
    option_b = data_fixture.create_select_option(
        field=looked_up_field, value="B", color="red"
    )
    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(lookupfield=option_a, primaryfield="primary a")
    b = table2_model.objects.create(lookupfield=option_b, primaryfield="primary b")

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
        number_decimal_places=2,
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {
                        "id": a.id,
                        "value": {
                            "id": option_a.id,
                            "value": option_a.value,
                            "color": option_a.color,
                        },
                    },
                    {
                        "id": b.id,
                        "value": {
                            "id": option_b.id,
                            "value": option_b.value,
                            "color": option_b.color,
                        },
                    },
                ],
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_import_export_lookup_field_when_through_field_trashed(
    data_fixture, api_client
):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)
    id_mapping = {}

    target_field = data_fixture.create_text_field(name="target", table=table_b)
    table_a_model = table_a.get_model(attribute_names=True)
    table_b_model = table_b.get_model(attribute_names=True)
    row_1 = table_b_model.objects.create(primary="1", target="target 1")
    row_2 = table_b_model.objects.create(primary="2", target="target 2")

    row_a = table_a_model.objects.create(primary="a")
    row_a.link.add(row_1.id)
    row_a.link.add(row_2.id)
    row_a.save()

    lookup = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name="link",
        target_field_name="target",
    )

    FieldHandler().delete_field(user, link_field)

    lookup.refresh_from_db()
    lookup_field_type = field_type_registry.get_by_model(lookup)
    lookup_serialized = lookup_field_type.export_serialized(lookup)

    assert lookup_serialized["through_field_id"] is None
    assert lookup_serialized["through_field_name"] == link_field.name
    assert lookup_serialized["target_field_id"] is None
    assert lookup_serialized["target_field_name"] == target_field.name

    lookup.name = "rename to prevent import clash"
    lookup.save()

    lookup_field_imported = lookup_field_type.import_serialized(
        table_a,
        lookup_serialized,
        id_mapping,
    )
    assert lookup_field_imported.through_field is None
    assert lookup_field_imported.through_field_name == link_field.name
    assert lookup_field_imported.target_field is None
    assert lookup_field_imported.target_field_name == lookup.target_field_name
    assert lookup_field_imported.formula_type == BaserowFormulaInvalidType.type
    assert lookup_field_imported.error == "references the deleted or unknown field link"


@pytest.mark.django_db
def test_import_export_lookup_field_trashed_target_field(data_fixture, api_client):
    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user=user)
    id_mapping = {}

    target_field = data_fixture.create_text_field(name="target", table=table_b)
    table_a_model = table_a.get_model(attribute_names=True)
    table_b_model = table_b.get_model(attribute_names=True)
    row_1 = table_b_model.objects.create(primary="1", target="target 1")
    row_2 = table_b_model.objects.create(primary="2", target="target 2")

    row_a = table_a_model.objects.create(primary="a")
    row_a.link.add(row_1.id)
    row_a.link.add(row_2.id)
    row_a.save()

    lookup = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup",
        through_field_name="link",
        target_field_name="target",
    )

    FieldHandler().delete_field(user, target_field)

    lookup.refresh_from_db()
    lookup_field_type = field_type_registry.get_by_model(lookup)
    lookup_serialized = lookup_field_type.export_serialized(lookup)

    assert lookup_serialized["through_field_id"] == link_field.id
    assert lookup_serialized["through_field_name"] == link_field.name
    assert lookup_serialized["target_field_id"] is None
    assert lookup_serialized["target_field_name"] == target_field.name

    lookup.name = "rename to prevent import clash"
    lookup.save()

    lookup_field_imported = lookup_field_type.import_serialized(
        table_a,
        lookup_serialized,
        id_mapping,
    )
    assert lookup_field_imported.through_field.id == link_field.id
    assert lookup_field_imported.through_field_name == link_field.name
    assert lookup_field_imported.target_field is None
    assert lookup_field_imported.target_field_name == lookup.target_field_name
    assert lookup_field_imported.formula_type == BaserowFormulaInvalidType.type
    assert (
        lookup_field_imported.error
        == "references the deleted or unknown lookup field target in table table_b"
    )


@pytest.mark.django_db()
def test_import_export_tables_with_lookup_fields(
    data_fixture, django_assert_num_queries
):
    user = data_fixture.create_user()
    imported_group = data_fixture.create_group(user=user)
    database = data_fixture.create_database_application(user=user, name="Placeholder")
    table = data_fixture.create_database_table(name="Example", database=database)
    customers_table = data_fixture.create_database_table(
        name="Customers", database=database
    )
    customer_name = data_fixture.create_text_field(table=customers_table, primary=True)
    customer_age = data_fixture.create_number_field(table=customers_table)
    field_handler = FieldHandler()
    core_handler = CoreHandler()
    link_row_field = field_handler.create_field(
        user=user,
        table=table,
        name="Link Row",
        type_name="link_row",
        link_row_table=customers_table,
    )

    row_handler = RowHandler()
    c_row = row_handler.create_row(
        user=user,
        table=customers_table,
        values={
            f"field_{customer_name.id}": "mary",
            f"field_{customer_age.id}": 65,
        },
    )
    c_row_2 = row_handler.create_row(
        user=user,
        table=customers_table,
        values={
            f"field_{customer_name.id}": "bob",
            f"field_{customer_age.id}": 67,
        },
    )
    row = row_handler.create_row(
        user=user,
        table=table,
        values={f"field_{link_row_field.id}": [c_row.id, c_row_2.id]},
    )

    lookup_field = field_handler.create_field(
        user=user,
        table=table,
        name="lookup",
        type_name="lookup",
        through_field_id=link_row_field.id,
        target_field_id=customer_age.id,
    )

    exported_applications = core_handler.export_group_applications(
        database.group, BytesIO()
    )
    imported_applications, id_mapping = core_handler.import_applications_to_group(
        imported_group, exported_applications, BytesIO(), None
    )
    imported_database = imported_applications[0]
    imported_tables = imported_database.table_set.all()
    imported_table = imported_tables[0]

    imported_lookup_field = imported_table.field_set.get(
        name=lookup_field.name
    ).specific
    imported_through_field = imported_table.field_set.get(
        name=link_row_field.name
    ).specific
    imported_target_field = imported_through_field.link_row_table.field_set.get(
        name=customer_age.name
    ).specific
    assert imported_lookup_field.formula == lookup_field.formula
    assert imported_lookup_field.formula_type == BaserowFormulaArrayType.type
    assert imported_lookup_field.array_formula_type == BaserowFormulaNumberType.type
    assert imported_lookup_field.through_field.name == link_row_field.name
    assert imported_lookup_field.target_field.name == customer_age.name
    assert imported_lookup_field.through_field_name == link_row_field.name
    assert imported_lookup_field.target_field_name == customer_age.name
    assert imported_lookup_field.target_field_id == imported_target_field.id
    assert imported_lookup_field.through_field_id == imported_through_field.id

    imported_table_model = imported_table.get_model(attribute_names=True)
    imported_rows = imported_table_model.objects.all()
    assert imported_rows.count() == 1
    imported_row = imported_rows.first()
    assert imported_row.id == row.id
    assert len(imported_row.lookup) == 2
    assert {"id": c_row.id, "value": 65} in imported_row.lookup
    assert {"id": c_row_2.id, "value": 67} in imported_row.lookup


@pytest.mark.django_db
def test_can_create_new_row_with_immediate_link_row_values_and_lookup_will_match(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table_a, table_b, link_field = data_fixture.create_two_linked_tables(user)

    table_b_model = table_b.get_model(attribute_names=True)
    b_row_1 = table_b_model.objects.create(primary="1")
    b_row_2 = table_b_model.objects.create(primary="2")

    lookup_field = FieldHandler().create_field(
        user,
        table_a,
        "lookup",
        name="lookup_field",
        through_field_id=link_field.id,
        target_field_name="primary",
    )
    assert lookup_field.error is None

    response = api_client.post(
        reverse("api:database:rows:list", kwargs={"table_id": table_a.id}),
        {f"field_{link_field.id}": [b_row_1.id, b_row_2.id]},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    lookup_values = response.json()[f"field_{lookup_field.id}"]
    assert {"id": b_row_1.id, "value": "1"} in lookup_values
    assert {"id": b_row_2.id, "value": "2"} in lookup_values

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table_a.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    lookup_values = response.json()["results"][0][f"field_{lookup_field.id}"]
    assert {"id": b_row_1.id, "value": "1"} in lookup_values
    assert {"id": b_row_2.id, "value": "2"} in lookup_values


@pytest.mark.django_db
def test_moving_a_looked_up_row_updates_the_order(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:move",
            kwargs={"table_id": table2.id, "row_id": a.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": b.id, "value": "primary b"},
                    {"id": a.id, "value": "primary a"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": b.id, "value": "2022-02-03"},
                    {"id": a.id, "value": "2021-02-01"},
                ],
                f"field_{string_agg.id}": "02/03/2022, 02/01/2021",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_can_modify_row_containing_lookup(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(user=user, database=table.database)
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    table_long_field = data_fixture.create_long_text_field(
        name="long",
        table=table,
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{table_long_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table.id, "row_id": table_row.id},
        ),
        {f"field_{table_primary_field.id}": "other"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.patch(
        reverse(
            "api:database:rows:item",
            kwargs={"table_id": table.id, "row_id": table_row.id},
        ),
        {f"field_{table_long_field.id}": "other"},
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": "other",
                f"field_{table_long_field.id}": "other",
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }


@pytest.mark.django_db
def test_deleting_restoring_lookup_target_works(
    data_fixture, api_client, django_assert_num_queries
):

    user, token = data_fixture.create_user_and_token()
    table = data_fixture.create_database_table(user=user)
    table2 = data_fixture.create_database_table(
        user=user, database=table.database, name="table 2"
    )
    table_primary_field = data_fixture.create_text_field(
        name="p", table=table, primary=True
    )
    data_fixture.create_text_field(name="primaryfield", table=table2, primary=True)
    looked_up_field = data_fixture.create_date_field(
        name="lookupfield",
        table=table2,
        date_include_time=False,
        date_format="US",
    )

    linkrowfield = FieldHandler().create_field(
        user,
        table,
        "link_row",
        name="linkrowfield",
        link_row_table=table2,
    )

    table2_model = table2.get_model(attribute_names=True)
    a = table2_model.objects.create(
        lookupfield=f"2021-02-01", primaryfield="primary " "a", order=0
    )
    b = table2_model.objects.create(
        lookupfield=f"2022-02-03", primaryfield="primary " "b", order=1
    )

    table_model = table.get_model(attribute_names=True)

    table_row = table_model.objects.create()
    table_row.linkrowfield.add(a.id)
    table_row.linkrowfield.add(b.id)
    table_row.save()

    lookup_field = FieldHandler().create_field(
        user,
        table,
        "lookup",
        name="lookup_field",
        through_field_id=linkrowfield.id,
        target_field_id=looked_up_field.id,
    )
    string_agg = FieldHandler().create_field(
        user,
        table,
        "formula",
        name="string_agg",
        formula='join(totext(field("lookup_field")), ", ")',
    )
    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }

    response = api_client.delete(
        reverse(
            "api:database:fields:item",
            kwargs={"field_id": looked_up_field.id},
        ),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_200_OK

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": None,
                f"field_{string_agg.id}": None,
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "invalid"
    assert (
        lookup_field.error
        == "references the deleted or unknown lookup field lookupfield in table table 2"
    )
    assert lookup_field.target_field is None
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "invalid"
    assert (
        string_agg.error
        == "references the deleted or unknown lookup field lookupfield in table table 2"
    )

    response = api_client.patch(
        reverse(
            "api:trash:restore",
        ),
        {
            "trash_item_type": "field",
            "trash_item_id": looked_up_field.id,
        },
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.status_code == HTTP_204_NO_CONTENT

    response = api_client.get(
        reverse("api:database:rows:list", kwargs={"table_id": table.id}),
        format="json",
        HTTP_AUTHORIZATION=f"JWT {token}",
    )
    assert response.json() == {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [
            {
                f"field_{table_primary_field.id}": None,
                f"field_{linkrowfield.id}": [
                    {"id": a.id, "value": "primary a"},
                    {"id": b.id, "value": "primary b"},
                ],
                f"field_{lookup_field.id}": [
                    {"id": a.id, "value": "2021-02-01"},
                    {"id": b.id, "value": "2022-02-03"},
                ],
                f"field_{string_agg.id}": "02/01/2021, 02/03/2022",
                "id": table_row.id,
                "order": "1.00000000000000000000",
            }
        ],
    }
    lookup_field.refresh_from_db()
    assert lookup_field.formula_type == "array"
    assert lookup_field.array_formula_type == "date"
    assert lookup_field.error is None
    assert lookup_field.target_field.id == looked_up_field.id
    assert lookup_field.target_field_name == looked_up_field.name
    assert lookup_field.through_field.id == linkrowfield.id

    string_agg.refresh_from_db()
    assert string_agg.formula_type == "text"
    assert string_agg.error is None
