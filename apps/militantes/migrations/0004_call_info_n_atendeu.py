from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('militantes', '0003_militantescallinfo_militantes_potencial_votante_id_and_more'),
    ]

    operations = [
        # militantes_call_info is an unmanaged table; add n_atendeu via SQL.
        # n_encontrado already exists in the legacy schema.
        migrations.RunSQL(
            sql=[
                "ALTER TABLE militantes_call_info ADD COLUMN IF NOT EXISTS n_atendeu smallint NULL;",
            ],
            reverse_sql=[
                "ALTER TABLE militantes_call_info DROP COLUMN IF EXISTS n_atendeu;",
            ],
        ),
    ]
