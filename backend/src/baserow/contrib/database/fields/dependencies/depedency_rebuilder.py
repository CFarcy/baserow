from typing import Tuple

from django.db.models import Q

from baserow.contrib.database.fields import models as field_models
from baserow.contrib.database.fields.dependencies.circular_reference_checker import (
    will_cause_circular_dep,
)
from baserow.contrib.database.fields.dependencies.exceptions import (
    CircularFieldDependencyError,
    SelfReferenceFieldDependencyError,
)
from baserow.contrib.database.fields.dependencies.models import FieldDependency
from baserow.contrib.database.fields.field_cache import FieldCache


def break_dependencies_for_field(field):
    """
    Given a specific field ensures no fields depend on it any more, and if they do
    those dependencies are set to be broken and only reference the field name.

    :param field: The field whose dependants will have their relationships broken for.
    """

    from baserow.contrib.database.fields.models import LinkRowField

    FieldDependency.objects.filter(dependant=field).delete()
    field.dependants.update(dependency=None, broken_reference_field_name=field.name)
    if isinstance(field, LinkRowField):
        field.vias.update(
            dependency=None, broken_reference_field_name=field.name, via=None
        )


def update_fields_with_broken_references(field: "field_models.Field"):
    """
    Checks to see if there are any fields which should now depend on `field` if it's
    name has changed to match a broken reference.

    :param field: The field that has potentially just been renamed.
    :return: True if some fields were found which now depend on field, False otherwise.
    """

    broken_dependencies_fixed_by_fields_name = FieldDependency.objects.filter(
        Q(
            dependant__table=field.table,
            broken_reference_field_name=field.name,
        )
        | Q(
            via__link_row_table=field.table,
            broken_reference_field_name=field.name,
        )
    )
    updated_deps = []
    for dep in broken_dependencies_fixed_by_fields_name:
        if not will_cause_circular_dep(dep.dependant, field):
            dep.dependency = field
            dep.broken_reference_field_name = None
            updated_deps.append(dep)
    FieldDependency.objects.bulk_update(
        updated_deps, ["dependency", "broken_reference_field_name"]
    )

    return len(updated_deps) > 0


def _construct_dependency(field_instance, dependency, field_lookup_cache):
    if isinstance(dependency, Tuple):
        (
            via_field_name,
            dependency,
        ) = dependency
    else:
        via_field_name = None

    if field_instance.name == dependency and via_field_name is None:
        raise SelfReferenceFieldDependencyError()

    table = field_instance.table
    if via_field_name is None:
        dependency_field = field_lookup_cache.lookup_by_name(table, dependency)
        if dependency_field is None:
            return [
                FieldDependency(
                    dependant=field_instance, broken_reference_field_name=dependency
                )
            ]
        else:
            return [
                FieldDependency(
                    dependant=field_instance, dependency=dependency_field, via=None
                )
            ]
    else:
        via_field = field_lookup_cache.lookup_by_name(table, via_field_name)
        if via_field is None:
            # We are depending on a non existent via field so we have no idea what
            # the target table is. Just create a single broken dependency to the via
            # field and depend on that.
            return [
                FieldDependency(
                    dependant=field_instance, broken_reference_field_name=via_field_name
                )
            ]
        else:
            from baserow.contrib.database.fields.models import LinkRowField

            if not isinstance(via_field, LinkRowField):
                # Depend on the via field directly so if it is renamed/deleted/changed
                # we get notified
                return [FieldDependency(dependant=field_instance, dependency=via_field)]
            else:
                target_table = via_field.link_row_table
                target_field = field_lookup_cache.lookup_by_name(
                    target_table, dependency
                )
                if target_field is None:
                    return [
                        FieldDependency(
                            dependant=field_instance,
                            broken_reference_field_name=dependency,
                            via=via_field,
                        )
                    ]
                else:
                    deps = []
                    if field_instance.id != via_field.id:
                        # Depend directly on the via field also so if it is renamed or
                        # changes we get notified.
                        deps.append(
                            FieldDependency(
                                dependant=field_instance, dependency=via_field, via=None
                            )
                        )
                    deps.append(
                        FieldDependency(
                            dependant=field_instance,
                            dependency=target_field,
                            via=via_field,
                        )
                    )
                    return deps


def rebuild_field_dependencies(
    field_instance,
    field_lookup_cache: FieldCache,
):
    """
    Deletes all existing dependencies a field has and resets them to the ones
    defined by the field_instances FieldType.get_field_dependencies. Does not
    affect any dependencies from other fields to this field.

    :param field_instance: The field whose dependencies to change.
    :param field_lookup_cache: A cache which will be used to lookup the actual
        fields referenced by any provided field dependencies.
    """

    from baserow.contrib.database.fields.registries import field_type_registry

    field_type = field_type_registry.get_by_model(field_instance)
    field_dependencies = field_type.get_field_dependencies(
        field_instance, field_lookup_cache
    )

    new_dependencies = []
    if field_dependencies is not None:
        for dependency in field_dependencies:
            new_dependencies += _construct_dependency(
                field_instance, dependency, field_lookup_cache
            )
    current_dependencies = field_instance.dependencies.all()

    # The str of a dependency can be used to compare two dependencies to see if they
    # are functionally the same.
    current_deps_by_str = {str(dep): dep for dep in current_dependencies}
    new_deps_by_str = {str(dep): dep for dep in new_dependencies}
    new_dependencies_to_create = []

    for new_dep_str, new_dep in new_deps_by_str.items():
        try:
            # By removing from current_deps_by_str once we have finished the loop
            # it will contain all the old dependencies we need to delete.
            current_deps_by_str.pop(new_dep_str)
        except KeyError:
            # The new dependency does not exist in the current dependencies so we must
            # create it.
            new_dependencies_to_create.append(new_dep)

    for dep in new_dependencies_to_create:
        if dep.dependency is not None and will_cause_circular_dep(
            field_instance, dep.dependency
        ):
            raise CircularFieldDependencyError()

    FieldDependency.objects.bulk_create(new_dependencies_to_create)
    # All new dependencies will have been removed from current_deps_by_str and so any
    # remaining ones are old dependencies which should no longer exist. Delete them.
    delete_ids = [dep.id for dep in current_deps_by_str.values()]
    FieldDependency.objects.filter(pk__in=delete_ids).delete()


def check_for_circular(
    field_instance,
    field_lookup_cache: FieldCache,
):
    from baserow.contrib.database.fields.registries import field_type_registry

    field_type = field_type_registry.get_by_model(field_instance)
    field_dependencies = field_type.get_field_dependencies(
        field_instance, field_lookup_cache
    )
    if field_dependencies is not None:
        for dependency in field_dependencies:
            dependency_field = _get_dependency_field(
                dependency, field_instance, field_lookup_cache
            )
            if dependency_field is not None:
                if field_instance.name == dependency_field.name:
                    raise SelfReferenceFieldDependencyError()

                if will_cause_circular_dep(field_instance, dependency_field):
                    raise CircularFieldDependencyError()


def _get_dependency_field(dependency, field_instance, field_lookup_cache):
    if isinstance(dependency, Tuple):
        (
            via_field_name,
            dependency,
        ) = dependency
        via_field = field_lookup_cache.lookup_by_name(
            field_instance.table, via_field_name
        )
        if via_field is not None:
            return field_lookup_cache.lookup_by_name(
                via_field.link_row_table, dependency
            )
        else:
            return None
    else:
        return field_lookup_cache.lookup_by_name(field_instance.table, dependency)
