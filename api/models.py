from django.db import models
from django.contrib.auth.models import User


class Farm(models.Model):
    """
    Farm model representing a farm owned by a user.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farms')
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    flock_size = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.user.username}"

    class Meta:
        ordering = ['-created_at']


class DiagnosisResult(models.Model):
    """
    DiagnosisResult model representing a disease diagnosis result from an image.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='diagnoses')
    farm = models.ForeignKey(Farm, on_delete=models.SET_NULL, null=True, blank=True, related_name='diagnoses')
    image = models.ImageField(upload_to='diagnosis_images/', null=True, blank=True)
    disease_name = models.CharField(max_length=255)
    confidence = models.FloatField()
    source = models.CharField(max_length=20, default='ai')
    status = models.CharField(max_length=20, default='Alert')
    description = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.disease_name} - {self.confidence:.2f}% - {self.user.username}"

    class Meta:
        ordering = ['-created_at']

