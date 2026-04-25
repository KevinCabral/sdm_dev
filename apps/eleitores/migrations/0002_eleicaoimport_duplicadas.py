from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eleitores", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="eleicaoimport",
            name="duplicadas",
            field=models.IntegerField(default=0),
        ),
    ]
