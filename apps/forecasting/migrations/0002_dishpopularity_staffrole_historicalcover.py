import django.core.validators
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecasting', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DishPopularity',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('dish_name', models.CharField(max_length=200, unique=True)),
                ('average_orders_percentage', models.DecimalField(
                    decimal_places=2,
                    max_digits=5,
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(100),
                    ],
                )),
            ],
            options={
                'verbose_name_plural': 'dish popularities',
                'ordering': ['-average_orders_percentage'],
            },
        ),
        migrations.CreateModel(
            name='StaffRole',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('role', models.CharField(
                    choices=[('waiter', 'Waiter'), ('chef', 'Chef'), ('bartender', 'Bartender'), ('manager', 'Manager'), ('cashier', 'Cashier')],
                    max_length=30,
                    unique=True,
                )),
                ('covers_per_staff', models.PositiveIntegerField()),
            ],
            options={
                'ordering': ['role'],
            },
        ),
        migrations.CreateModel(
            name='HistoricalCover',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('hour', models.PositiveSmallIntegerField(
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(23),
                    ],
                )),
                ('covers', models.PositiveIntegerField()),
                ('weather', models.CharField(blank=True, choices=[('sunny', 'Sunny'), ('cloudy', 'Cloudy'), ('rainy', 'Rainy'), ('snowy', 'Snowy')], max_length=20)),
                ('is_weekend', models.BooleanField(default=False)),
                ('special_event', models.CharField(blank=True, max_length=200)),
            ],
            options={
                'ordering': ['-date', 'hour'],
                'indexes': [
                    models.Index(fields=['date'], name='forecasting_date_bab6b9_idx'),
                    models.Index(fields=['is_weekend'], name='forecasting_is_week_1eaa74_idx'),
                ],
                'unique_together': {('date', 'hour')},
            },
        ),
    ]
