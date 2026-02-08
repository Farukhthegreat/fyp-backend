from django.contrib import admin
from .models import Farm, DiagnosisResult


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    """
    Admin interface for Farm model.
    """
    list_display = ['name', 'location', 'flock_size', 'user', 'created_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'location', 'user__username', 'user__email']
    date_hierarchy = 'created_at'


@admin.register(DiagnosisResult)
class DiagnosisResultAdmin(admin.ModelAdmin):
    """
    Admin interface for DiagnosisResult model.
    """
    list_display = ['disease_name', 'confidence', 'user', 'farm', 'created_at']
    list_filter = ['disease_name', 'created_at', 'user']
    search_fields = ['disease_name', 'user__username', 'user__email']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']

