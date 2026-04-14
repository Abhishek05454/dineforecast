import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ForecastAccuracy',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField(unique=True)),
                ('predicted_covers', models.PositiveIntegerField()),
                ('actual_covers', models.PositiveIntegerField()),
                ('reason', models.TextField(blank=True)),
            ],
            options={
                'verbose_name_plural': 'forecast accuracies',
                'ordering': ['-date'],
            },
        ),
    ]
