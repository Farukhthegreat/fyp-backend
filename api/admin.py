from django.contrib import admin
from .models import (
    Farm, DiagnosisResult, Supplier, SupplierProduct,
    Expert, ChatRoom, ChatMessage, DailyTask, TaskCompletion, Article
)


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'flock_size', 'user', 'created_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'location', 'user__username', 'user__email']
    date_hierarchy = 'created_at'


@admin.register(DiagnosisResult)
class DiagnosisResultAdmin(admin.ModelAdmin):
    list_display = ['disease_name', 'confidence', 'user', 'farm', 'created_at']
    list_filter = ['disease_name', 'created_at', 'user']
    search_fields = ['disease_name', 'user__username', 'user__email']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']


class SupplierProductInline(admin.TabularInline):
    model = SupplierProduct
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'supplier_type', 'location', 'phone', 'is_active']
    list_filter = ['supplier_type', 'is_active']
    search_fields = ['name', 'location']
    inlines = [SupplierProductInline]


@admin.register(Expert)
class ExpertAdmin(admin.ModelAdmin):
    list_display = ['user', 'specialization', 'whatsapp', 'is_available']
    list_filter = ['specialization', 'is_available']


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ['farmer', 'expert', 'created_at', 'updated_at']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['room', 'sender', 'message', 'is_read', 'created_at']
    list_filter = ['is_read']


@admin.register(DailyTask)
class DailyTaskAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'time_of_day', 'season', 'is_active']
    list_filter = ['category', 'time_of_day', 'season', 'is_active']


@admin.register(TaskCompletion)
class TaskCompletionAdmin(admin.ModelAdmin):
    list_display = ['user', 'task', 'date', 'completed_at']
    list_filter = ['date']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'is_published', 'created_at']
    list_filter = ['category', 'is_published']
    search_fields = ['title', 'content']

