from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('potenciais_votantes', '0002_potencialvotante_is_contactado'),
    ]

    operations = [
        migrations.AddField(
            model_name='potencialvotante',
            name='programa',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='potencialvotante',
            name='concelho',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
