from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from core.models import BaseModel


class GuestFeedback(BaseModel):
    class Category(models.TextChoices):
        FOOD = "food", "Food Quality"
        SERVICE = "service", "Service"
        AMBIENCE = "ambience", "Ambience"
        VALUE = "value", "Value for Money"
        OVERALL = "overall", "Overall Experience"

    visit_date = models.DateField()
    category = models.CharField(max_length=20, choices=Category.choices)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True)
    guest_name = models.CharField(max_length=150, blank=True)
    is_resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ["-visit_date", "-created_at"]

    def __str__(self):
        return f"{self.category} | {self.rating}/5 | {self.visit_date}"


class FeedbackResponse(BaseModel):
    feedback = models.OneToOneField(
        GuestFeedback, on_delete=models.CASCADE, related_name="response"
    )
    responded_by = models.CharField(max_length=150)
    message = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Response to {self.feedback}"


class ForecastAccuracy(BaseModel):
    date = models.DateField(unique=True)
    predicted_covers = models.PositiveIntegerField()
    actual_covers = models.PositiveIntegerField()
    reason = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "forecast accuracies"
        ordering = ["-date"]

    @property
    def variance(self):
        return self.actual_covers - self.predicted_covers

    @property
    def accuracy_percentage(self):
        if self.predicted_covers == 0:
            return None
        accuracy = (1 - abs(self.variance) / self.predicted_covers) * 100
        return round(max(0, accuracy), 2)

    def __str__(self):
        return f"{self.date} | predicted {self.predicted_covers} | actual {self.actual_covers}"
