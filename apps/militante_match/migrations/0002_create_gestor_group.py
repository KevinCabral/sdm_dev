"""Create the `gestor_militantes` auth group.

Mirrors the convention from `apps.mesa.migrations.0002_create_api_groups`:
groups exist as plain `auth.Group` rows; their privileges are enforced by
the DRF permission classes in `api.permissions`.
"""
from django.db import migrations


GROUPS = ["gestor_militantes"]


def create_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in GROUPS:
        Group.objects.get_or_create(name=name)


def remove_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=GROUPS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("militante_match", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_groups, remove_groups),
    ]
