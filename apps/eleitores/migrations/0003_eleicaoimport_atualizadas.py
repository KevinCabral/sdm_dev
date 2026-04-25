from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eleitores", "0002_eleicaoimport_duplicadas"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleicaoimport",
            name="atualizadas",
            field=models.IntegerField(default=0),
        ),
    ]
